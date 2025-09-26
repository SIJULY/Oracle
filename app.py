import os, json, threading, string, random, base64, time, logging, uuid, sqlite3, configparser
from flask import Flask, render_template, jsonify, request, session, g, redirect, url_for
from functools import wraps
import oci
from oci.core.models import CreatePublicIpDetails, PublicIp, CreateIpv6Details
from oci.exceptions import ServiceError, ConfigFileNotFound, InvalidPrivateKey, MissingPrivateKeyPassphrase, HttpResponseError

app = Flask(__name__)
app.secret_key = 'a_very_secret_key_for_oci_panel'
PASSWORD = "You22kme#12345" # 【重要】请修改为您自己的登录密码
KEYS_FILE = "oci_profiles.json"
DATABASE = 'oci_tasks.db'

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- 数据库设置与辅助函数 ---
def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE, check_same_thread=False)
        db.row_factory = sqlite3.Row
    return db
@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None: db.close()
def init_db():
    if not os.path.exists(DATABASE):
        with app.app_context():
            db = get_db()
            db.cursor().executescript("CREATE TABLE tasks (id TEXT PRIMARY KEY, status TEXT NOT NULL, result TEXT);")
            db.commit()
            app.logger.info("任务数据库已初始化。")
def query_db(query, args=(), one=False):
    db = sqlite3.connect(DATABASE); db.row_factory = sqlite3.Row; cur = db.execute(query, args)
    rv = cur.fetchall(); cur.close(); db.close()
    return (rv[0] if rv else None) if one else rv

# --- 核心辅助函数 ---
def load_profiles():
    if not os.path.exists(KEYS_FILE): return {}
    try:
        with open(KEYS_FILE, 'r', encoding='utf-8') as f: content = f.read(); return json.loads(content) if content else {}
    except (IOError, json.JSONDecodeError): return {}
def save_profiles(profiles):
    with open(KEYS_FILE, 'w', encoding='utf-8') as f: json.dump(profiles, f, indent=4, ensure_ascii=False)
def generate_password(length=16):
    chars = string.ascii_letters + string.digits + "!@#$%^&*()_+=-`~[]{};:,.<>?"
    return ''.join(random.choice(chars) for i in range(length))
def get_oci_clients(profile_config):
    try:
        oci.config.validate_config(profile_config)
        return { "identity": oci.identity.IdentityClient(profile_config), "compute": oci.core.ComputeClient(profile_config), "vnet": oci.core.VirtualNetworkClient(profile_config), "bs": oci.core.BlockstorageClient(profile_config) }, None
    except Exception as e:
        return None, f"创建OCI客户端失败: {str(e)}"

# --- 装饰器 ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_logged_in" not in session:
            if request.path.startswith('/api/'): return jsonify({"error": "用户未登录"}), 401
            return redirect('/login')
        return f(*args, **kwargs)
    return decorated_function
def oci_clients_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'oci_profile_alias' not in session: return jsonify({"error": "请先选择一个OCI账号"}), 403
        alias = session['oci_profile_alias']
        profile_config = load_profiles().get(alias)
        if not profile_config: return jsonify({"error": f"账号 '{alias}' 未找到"}), 404
        clients, error = get_oci_clients(profile_config)
        if error: return jsonify({"error": error}), 500
        g.oci_clients = clients
        g.oci_config = profile_config
        return f(*args, **kwargs)
    return decorated_function

# --- 页面路由 ---
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.form.get("password") == PASSWORD:
            session["user_logged_in"] = True
            return redirect(url_for('index'))
        else:
            return render_template("login.html", error="密码错误")
    return render_template("login.html")
@app.route("/logout")
def logout():
    session.clear(); return redirect('/login')
@app.route("/")
@login_required
def index():
    return render_template("index.html")

# --- API 路由 ---
@app.route("/api/profiles/import_ini", methods=["POST"])
@login_required
def import_profiles_from_ini():
    file = request.files.get('file')
    if not file: return jsonify({"error": "未提供文件"}), 400
    try:
        content = file.read().decode('utf-8')
        config_parser = configparser.ConfigParser()
        config_parser.read_string(content)
        profiles = config_parser.sections()
        if 'DEFAULT' in config_parser and bool(config_parser['DEFAULT']):
            if 'DEFAULT' not in profiles: profiles.insert(0, 'DEFAULT')
        
        profiles_data = {name: dict(config_parser.items(name)) for name in profiles}
        return jsonify(profiles_data)
    except Exception as e:
        return jsonify({"error": f"解析INI文件失败: {str(e)}"}), 500

@app.route("/api/profiles", methods=["GET", "POST"])
@login_required
def manage_profiles():
    profiles = load_profiles()
    if request.method == "GET": return jsonify(profiles)
    data = request.json
    for alias, profile_data in data.items():
        profiles[alias] = profile_data
    save_profiles(profiles)
    return jsonify({"success": True})

@app.route("/api/profiles/<alias>", methods=["DELETE"])
@login_required
def delete_profile(alias):
    profiles = load_profiles()
    if alias not in profiles: return jsonify({"error": "账号未找到"}), 404
    del profiles[alias]
    save_profiles(profiles)
    if session.get('oci_profile_alias') == alias: session.pop('oci_profile_alias', None)
    return jsonify({"success": True})

@app.route("/api/session", methods=["POST", "GET", "DELETE"])
@login_required
def oci_session():
    if request.method == "POST":
        alias = request.json.get("alias")
        if not alias or alias not in load_profiles(): return jsonify({"error": "无效的账号别名"}), 400
        session['oci_profile_alias'] = alias
        profile_config = load_profiles().get(alias)
        _, error = get_oci_clients(profile_config)
        if error: return jsonify({"error": f"连接验证失败: {error}"}), 400
        return jsonify({"success": True, "alias": alias})
    if request.method == "GET":
        alias = session.get('oci_profile_alias')
        if alias: return jsonify({"logged_in": True, "alias": alias})
        return jsonify({"logged_in": False})
    if request.method == "DELETE":
        session.pop('oci_profile_alias', None); return jsonify({"success": True})

@app.route('/api/instances')
@login_required
@oci_clients_required
def get_instances():
    try:
        compute_client = g.oci_clients['compute']
        vnet_client = g.oci_clients['vnet']
        bs_client = g.oci_clients['bs']
        compartment_id = g.oci_config['tenancy']
        
        instances = oci.pagination.list_call_get_all_results(compute_client.list_instances, compartment_id=compartment_id).data
        instance_details_list = []
        for instance in instances:
             instance_data = {
                 "display_name": instance.display_name, "id": instance.id, "lifecycle_state": instance.lifecycle_state,
                 "region": instance.region, "shape": instance.shape, "availability_domain": instance.availability_domain,
                 "time_created": instance.time_created.isoformat() if instance.time_created else None,
                 "ocpus": instance.shape_config.ocpus, "memory_in_gbs": instance.shape_config.memory_in_gbs,
                 "private_ip": "N/A", "public_ip": "N/A", "ipv6_address": "N/A",
                 "boot_volume_size_gb": "N/A", "vnic_id": None, "subnet_id": None
             }
             vnic_attachments = compute_client.list_vnic_attachments(compartment_id, instance_id=instance.id).data
             if vnic_attachments:
                 vnic_id = vnic_attachments[0].vnic_id
                 subnet_id = vnic_attachments[0].subnet_id
                 instance_data['vnic_id'] = vnic_id
                 instance_data['subnet_id'] = subnet_id
                 vnic = vnet_client.get_vnic(vnic_id).data
                 instance_data['private_ip'] = vnic.private_ip
                 instance_data['public_ip'] = vnic.public_ip or "无"
                 ipv6s = vnet_client.list_ipv6s(vnic_id=vnic_id).data
                 instance_data['ipv6_address'] = ipv6s[0].ip_address if ipv6s else "无"

             boot_vol_attachments = compute_client.list_boot_volume_attachments(instance.availability_domain, compartment_id, instance_id=instance.id).data
             if boot_vol_attachments:
                 boot_vol = bs_client.get_boot_volume(boot_vol_attachments[0].boot_volume_id).data
                 instance_data['boot_volume_size_gb'] = f"{int(boot_vol.size_in_gbs)} GB"

             instance_details_list.append(instance_data)

        return jsonify(instance_details_list)
    except ServiceError as e:
        return jsonify({"error": f"获取实例列表失败: {e.code} - {e.message}"}), 500
    except Exception as e:
        return jsonify({"error": f"获取实例列表时发生未知错误: {str(e)}"}), 500

@app.route('/api/instance-action', methods=['POST'])
@login_required
@oci_clients_required
def instance_action():
    data = request.json
    action = data.get('action')
    instance_id = data.get('instance_id')
    if not action or not instance_id: return jsonify({"error": "Action and instance_id are required"}), 400
    
    task_id = str(uuid.uuid4())
    db = get_db()
    db.execute('INSERT INTO tasks (id, status) VALUES (?, ?)', (task_id, 'pending'))
    db.commit()

    task_kwargs = { 'task_id': task_id, 'profile_config': g.oci_config, 'action': action, 'instance_id': instance_id, 'data': data }
    threading.Thread(target=_instance_action_task, kwargs=task_kwargs).start()
    return jsonify({"message": f"'{action}' 请求已提交...", "task_id": task_id})

def _instance_action_task(task_id, profile_config, action, instance_id, data):
    with app.app_context():
        db = get_db()
        db.execute('UPDATE tasks SET status = ? WHERE id = ?', ('running', task_id)); db.commit()
        try:
            clients, error = get_oci_clients(profile_config)
            if error: raise Exception(error)
            
            action_upper = action.upper()
            result_message = ""

            if action_upper in ["START", "STOP", "SOFTRESET"]:
                clients['compute'].instance_action(instance_id=instance_id, action=action_upper)
                result_message = f"实例 {action_upper} 命令已发送。"
            elif action_upper == "TERMINATE":
                preserve = data.get('preserve_boot_volume', False)
                clients['compute'].terminate_instance(instance_id, preserve_boot_volume=preserve)
                result_message = "实例终止命令已发送。"
            elif action_upper == "CHANGE_IP":
                vnic_id = data.get('vnic_id')
                compartment_id = profile_config['tenancy']
                vnet_client = clients['vnet']
                private_ips = oci.pagination.list_call_get_all_results(vnet_client.list_private_ips, vnic_id=vnic_id).data
                primary_private_ip = next((p for p in private_ips if p.is_primary), None)
                if not primary_private_ip: raise Exception("未找到主私有IP")
                
                try:
                    pub_ip_details = oci.core.models.GetPublicIpByPrivateIpIdDetails(private_ip_id=primary_private_ip.id)
                    existing_pub_ip = vnet_client.get_public_ip_by_private_ip_id(pub_ip_details).data
                    if existing_pub_ip.lifetime == "EPHEMERAL":
                        vnet_client.delete_public_ip(existing_pub_ip.id)
                        time.sleep(5)
                except ServiceError as e:
                    if e.status != 404: raise
                
                new_pub_ip_details = CreatePublicIpDetails(compartment_id=compartment_id, lifetime="EPHEMERAL", private_ip_id=primary_private_ip.id)
                new_pub_ip = vnet_client.create_public_ip(new_pub_ip_details).data
                result_message = f"更换IP请求成功，新IP: {new_pub_ip.ip_address}"
            
            db.execute('UPDATE tasks SET status = ?, result = ? WHERE id = ?', ('success', result_message, task_id)); db.commit()
        except Exception as e:
            error_message = f"操作 '{action}' 失败: {str(e)}"
            db.execute('UPDATE tasks SET status = ?, result = ? WHERE id = ?', ('failure', error_message, task_id)); db.commit()


@app.route('/api/create-instance', methods=['POST'])
@login_required
@oci_clients_required
def create_instance():
    task_id = str(uuid.uuid4())
    db = get_db()
    db.execute('INSERT INTO tasks (id, status) VALUES (?, ?)', (task_id, 'pending'))
    db.commit()
    
    data = request.json
    task_kwargs = { 'task_id': task_id, 'profile_config': g.oci_config, 'details': data }
    threading.Thread(target=_create_instance_task, kwargs=task_kwargs).start()
    return jsonify({"message": "创建实例请求已提交...", "task_id": task_id})

def _create_instance_task(task_id, profile_config, details):
    with app.app_context():
        db = get_db()
        db.execute('UPDATE tasks SET status = ? WHERE id = ?', ('running', task_id)); db.commit()
        try:
            clients, error = get_oci_clients(profile_config)
            if error: raise Exception(error)
            
            compute_client, identity_client = clients['compute'], clients['identity']
            tenancy_ocid = profile_config.get('tenancy')
            ads = oci.pagination.list_call_get_all_results(identity_client.list_availability_domains, compartment_id=tenancy_ocid).data
            if not ads: raise Exception("无法获取可用域")
            ad_name = ads[0].name
            
            subnet_id = profile_config.get('default_subnet_ocid')
            ssh_key = profile_config.get('default_ssh_public_key')
            if not subnet_id or not ssh_key: raise Exception("账号配置缺少默认子网或SSH公钥")

            os_name, os_version = details['os_name_version'].split('-')
            shape = details['shape']
            
            images = oci.pagination.list_call_get_all_results(
                compute_client.list_images, compartment_id=tenancy_ocid, operating_system=os_name,
                operating_system_version=os_version, shape=shape, sort_by="TIMECREATED", sort_order="DESC"
            ).data
            if not images: raise Exception(f"未找到兼容的镜像 for {os_name} {os_version}")
            image_ocid = images[0].id

            root_password = generate_password()
            user_data_encoded = base64.b64encode(f"""#cloud-config
password: {root_password}
chpasswd: {{ expire: False }}
ssh_pwauth: True
runcmd:
  - sed -i 's/^PermitRootLogin .*/PermitRootLogin yes/' /etc/ssh/sshd_config
  - sed -i 's/^#?PasswordAuthentication .*/PasswordAuthentication yes/' /etc/ssh/sshd_config
  - systemctl restart sshd || service sshd restart || service ssh restart
""".encode('utf-8')).decode('utf-8')

            base_name = details.get('display_name_prefix', 'Instance')
            instance_count = details.get('instance_count', 1)
            created_instances_info = []

            for i in range(instance_count):
                instance_name = f"{base_name}-{i+1}" if instance_count > 1 else base_name
                launch_details = oci.core.models.LaunchInstanceDetails(
                    compartment_id=tenancy_ocid, availability_domain=ad_name, shape=shape,
                    display_name=instance_name,
                    create_vnic_details=oci.core.models.CreateVnicDetails(subnet_id=subnet_id, assign_public_ip=True),
                    metadata={"ssh_authorized_keys": ssh_key, "user_data": user_data_encoded},
                    source_details=oci.core.models.InstanceSourceViaImageDetails(
                        image_id=image_ocid,
                        boot_volume_size_in_gbs=details['boot_volume_size']
                    ),
                    shape_config=oci.core.models.LaunchInstanceShapeConfigDetails(
                        ocpus=details.get('ocpus'), memory_in_gbs=details.get('memory_in_gbs')
                    ) if shape == "VM.Standard.A1.Flex" else None
                )
                instance = compute_client.launch_instance(launch_details).data
                created_instances_info.append(instance_name)
                if i < instance_count - 1: time.sleep(3)

            success_message = f"🎉 {len(created_instances_info)}个实例创建请求已发送!\n    - 实例名: {', '.join(created_instances_info)}\n    - Root 密码: {root_password} (所有实例通用)"
            db.execute('UPDATE tasks SET status = ?, result = ? WHERE id = ?', ('success', success_message, task_id))
            db.commit()
        except Exception as e:
            error_message = f"❌ 实例创建失败! \n    - 原因: {str(e)}"
            db.execute('UPDATE tasks SET status = ?, result = ? WHERE id = ?', ('failure', error_message, task_id))
            db.commit()

@app.route('/api/task_status/<task_id>')
@login_required
def task_status(task_id):
    task = query_db('SELECT * FROM tasks WHERE id = ?', [task_id], one=True)
    if task is None: return jsonify({'status': 'not_found'}), 404
    return jsonify({'status': task['status'], 'result': task['result']})

init_db()

if __name__ == '__main__':
    app.run(debug=True, port=5003)
