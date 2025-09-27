import os, json, threading, string, random, base64, time, logging, uuid, sqlite3, configparser, datetime
from flask import Flask, render_template, jsonify, request, session, g, redirect, url_for
from functools import wraps
import oci
from oci.core.models import CreateVcnDetails, CreateSubnetDetails, CreateInternetGatewayDetails, UpdateRouteTableDetails, RouteRule, CreatePublicIpDetails, CreateIpv6Details, UpdateInstanceDetails, UpdateInstanceShapeConfigDetails
from oci.exceptions import ServiceError
from celery import Celery

# --- Flask App and Celery Configuration ---
app = Flask(__name__)

# --- ↓↓↓ 本次唯一的修改点：添加下面的配置来禁用缓存 ↓↓↓ ---
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
app.config['TEMPLATES_AUTO_RELOAD'] = True
# --- ↑↑↑ 本次唯一的修改点：添加上面的配置来禁用缓存 ↑↑↑ ---

app.secret_key = 'a_very_secret_key_for_oci_panel'
app.config.update(
    CELERY_BROKER_URL='redis://localhost:6379/0',
    CELERY_RESULT_BACKEND='redis://localhost:6379/0'
)
celery = Celery(app.import_name, backend=app.config['CELERY_RESULT_BACKEND'], broker=app.config['CELERY_BROKER_URL'])
celery.conf.update(app.config)

# --- General Configuration & Helpers ---
PASSWORD = "You22kme#12345"
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
            db.cursor().executescript("CREATE TABLE tasks (id TEXT PRIMARY KEY, type TEXT, name TEXT, status TEXT NOT NULL, result TEXT, created_at TEXT);")
            db.commit()
            app.logger.info("任务数据库已初始化。")
    else:
        with app.app_context():
            db = get_db()
            cursor = db.cursor()
            cursor.execute("PRAGMA table_info(tasks)")
            columns = [info[1] for info in cursor.fetchall()]
            if 'created_at' not in columns:
                cursor.execute("ALTER TABLE tasks ADD COLUMN created_at TEXT")
            db.commit()
            app.logger.info("任务数据库已检查/更新。")


def query_db(query, args=(), one=False):
    db = sqlite3.connect(DATABASE); db.row_factory = sqlite3.Row; cur = db.execute(query, args)
    rv = cur.fetchall(); cur.close(); db.close()
    return (rv[0] if rv else None) if one else rv

# --- 核心辅助函数 ---
def load_profiles():
    if not os.path.exists(KEYS_FILE): return {}
    try:
        with open(KEYS_FILE, 'r', encoding='utf-8') as f: 
            content = f.read()
            if not content: return {}
            return json.loads(content)
    except (IOError, json.JSONDecodeError) as e:
        app.logger.error(f"FATAL: Could not read or parse {KEYS_FILE}: {e}")
        return {}

def save_profiles(profiles):
    with open(KEYS_FILE, 'w', encoding='utf-8') as f: json.dump(profiles, f, indent=4, ensure_ascii=False)

def generate_password(length=16):
    chars = string.ascii_letters + string.digits + "!@#$%^&*()_+=-`~[]{};:,.<>?"
    return ''.join(random.choice(chars) for i in range(length))

def get_oci_clients(profile_config):
    try:
        # The key_content needs to be written to a temporary file for the SDK to read
        if 'key_content' in profile_config and 'key_file' not in profile_config:
            key_file_path = f"/tmp/{uuid.uuid4()}.pem"
            with open(key_file_path, 'w') as key_file:
                key_file.write(profile_config['key_content'])
            os.chmod(key_file_path, 0o600)
            
            config_for_sdk = profile_config.copy()
            config_for_sdk['key_file'] = key_file_path
        else:
            config_for_sdk = profile_config

        oci.config.validate_config(config_for_sdk)
        clients = { 
            "identity": oci.identity.IdentityClient(config_for_sdk), 
            "compute": oci.core.ComputeClient(config_for_sdk), 
            "vnet": oci.core.VirtualNetworkClient(config_for_sdk), 
            "bs": oci.core.BlockstorageClient(config_for_sdk) 
        }

        if 'key_content' in profile_config and 'key_file' not in profile_config:
            if os.path.exists(key_file_path):
                os.remove(key_file_path)

        return clients, None
    except Exception as e:
        return None, f"创建OCI客户端失败: {str(e)}"

def _ensure_subnet_in_profile(alias, vnet_client, tenancy_ocid):
    profiles = load_profiles()
    profile_config = profiles.get(alias, {})
    subnet_id = profile_config.get('default_subnet_ocid')

    if subnet_id:
        try:
            get_subnet_response = vnet_client.get_subnet(subnet_id)
            if get_subnet_response.data.lifecycle_state == 'AVAILABLE':
                logging.info(f"使用账号 '{alias}' 中已配置的子网: ...{subnet_id[-12:]}")
                return subnet_id
        except ServiceError as e:
            if e.status == 404:
                logging.warning(f"配置文件中的子网 {subnet_id} 已不存在，将重新创建网络。")
            else:
                raise e

    logging.info(f"账号 '{alias}' 未配置可用子网，开始自动创建网络资源...")
    
    vcn_name = f"vcn-autocreated-{alias}-{random.randint(100, 999)}"
    vcn_details = CreateVcnDetails(
        cidr_block="10.0.0.0/16",
        display_name=vcn_name,
        compartment_id=tenancy_ocid
    )
    vcn = vnet_client.create_vcn(vcn_details).data
    oci.waiter.wait_for_resource(vnet_client, vnet_client.get_vcn(vcn.id), 'lifecycle_state', oci.core.models.Vcn.LIFECYCLE_STATE_AVAILABLE)
    logging.info(f"VCN '{vcn_name}' ({vcn.id}) 已创建。")

    ig_name = f"ig-autocreated-{alias}-{random.randint(100, 999)}"
    ig_details = CreateInternetGatewayDetails(
        display_name=ig_name,
        compartment_id=tenancy_ocid,
        is_enabled=True,
        vcn_id=vcn.id
    )
    ig = vnet_client.create_internet_gateway(ig_details).data
    oci.waiter.wait_for_resource(vnet_client, vnet_client.get_internet_gateway(ig.id), 'lifecycle_state', oci.core.models.InternetGateway.LIFECYCLE_STATE_AVAILABLE)
    logging.info(f"Internet Gateway '{ig_name}' ({ig.id}) 已创建。")

    route_table_id = vcn.default_route_table_id
    route_rule = RouteRule(destination="0.0.0.0/0", network_entity_id=ig.id)
    get_rt_response = vnet_client.get_route_table(route_table_id)
    route_rules = get_rt_response.data.route_rules
    route_rules.append(route_rule)
    update_rt_details = UpdateRouteTableDetails(route_rules=route_rules)
    vnet_client.update_route_table(route_table_id, update_rt_details)
    logging.info(f"已更新路由表以允许公网访问。")

    subnet_name = f"subnet-autocreated-{alias}-{random.randint(100, 999)}"
    subnet_details = CreateSubnetDetails(
        compartment_id=tenancy_ocid,
        vcn_id=vcn.id,
        cidr_block="10.0.1.0/24",
        display_name=subnet_name
    )
    subnet = vnet_client.create_subnet(subnet_details).data
    oci.waiter.wait_for_resource(vnet_client, vnet_client.get_subnet(subnet.id), 'lifecycle_state', oci.core.models.Subnet.LIFECYCLE_STATE_AVAILABLE)
    logging.info(f"子网 '{subnet_name}' ({subnet.id}) 已创建。")

    profiles[alias]['default_subnet_ocid'] = subnet.id
    save_profiles(profiles)
    logging.info(f"已将新创建的子网ID保存到账号 '{alias}' 的配置中。")

    return subnet.id

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
@app.route("/api/profiles", methods=["GET", "POST"])
@login_required
def manage_profiles():
    profiles = load_profiles()
    if request.method == "GET":
        return jsonify(list(profiles.keys()))
    
    data = request.json
    alias = data.get("alias")
    profile_data = data.get("profile_data")
    if not alias or not profile_data:
        return jsonify({"error": "别名和配置数据不能为空"}), 400
    
    profiles[alias] = profile_data
    save_profiles(profiles)
    return jsonify({"success": True, "alias": alias})

@app.route("/api/profiles/<alias>", methods=["GET", "DELETE"])
@login_required
def handle_single_profile(alias):
    profiles = load_profiles()
    if alias not in profiles:
        return jsonify({"error": "账号未找到"}), 404

    if request.method == "GET":
        return jsonify(profiles[alias])

    if request.method == "DELETE":
        del profiles[alias]
        save_profiles(profiles)
        if session.get('oci_profile_alias') == alias:
            session.pop('oci_profile_alias', None)
        return jsonify({"success": True})

@app.route('/api/tasks/snatching/running', methods=['GET'])
@login_required
def get_running_snatching_tasks():
    tasks = query_db("SELECT id, name, result, created_at FROM tasks WHERE type = 'snatch' AND status = 'running' ORDER BY created_at DESC")
    return jsonify([dict(task) for task in tasks])

@app.route('/api/tasks/snatching/completed', methods=['GET'])
@login_required
def get_completed_snatching_tasks():
    tasks = query_db("SELECT id, name, status, result, created_at FROM tasks WHERE type = 'snatch' AND (status = 'success' OR status = 'failure') ORDER BY created_at DESC LIMIT 50")
    return jsonify([dict(task) for task in tasks])

@app.route('/api/tasks/<task_id>', methods=['DELETE'])
@login_required
def delete_task_record(task_id):
    try:
        task = query_db("SELECT status FROM tasks WHERE id = ?", [task_id], one=True)
        if task and task['status'] in ['success', 'failure']:
            db = get_db()
            db.execute('DELETE FROM tasks WHERE id = ?', (task_id,))
            db.commit()
            return jsonify({"success": True, "message": "任务记录已删除。"})
        else:
            return jsonify({"error": "只能删除已完成或失败的任务记录。"}), 400
    except Exception as e:
        app.logger.error(f"删除任务记录 {task_id} 失败: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/tasks/<task_id>/stop', methods=['POST'])
@login_required
def stop_task(task_id):
    try:
        celery.control.revoke(task_id, terminate=True, signal='SIGKILL')
        db = get_db()
        db.execute('UPDATE tasks SET status = ?, result = ? WHERE id = ?', ('failure', '任务已被用户手动停止。', task_id))
        db.commit()
        return jsonify({"success": True, "message": f"停止任务 {task_id} 的请求已发送。"})
    except Exception as e:
        app.logger.error(f"停止任务 {task_id} 失败: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/session", methods=["POST", "GET", "DELETE"])
@login_required
def oci_session():
    if request.method == "POST":
        alias = request.json.get("alias")
        profiles = load_profiles()
        if not alias or alias not in profiles: return jsonify({"error": "无效的账号别名"}), 400
        session['oci_profile_alias'] = alias
        profile_config = profiles.get(alias)
        _, error = get_oci_clients(profile_config)
        if error: return jsonify({"error": f"连接验证失败: {error}"}), 400
        
        can_create_and_snatch = bool(profile_config.get('default_ssh_public_key'))
        return jsonify({"success": True, "alias": alias, "can_create": can_create_and_snatch, "can_snatch": can_create_and_snatch})

    if request.method == "GET":
        alias = session.get('oci_profile_alias')
        if alias:
            profiles = load_profiles()
            profile_config = profiles.get(alias, {})
            can_create_and_snatch = bool(profile_config.get('default_ssh_public_key'))
            return jsonify({"logged_in": True, "alias": alias, "can_create": can_create_and_snatch, "can_snatch": can_create_and_snatch})
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
                 "ocpus": instance.shape_config.ocpus if instance.shape_config and hasattr(instance.shape_config, 'ocpus') else 'N/A',
                 "memory_in_gbs": instance.shape_config.memory_in_gbs if instance.shape_config and hasattr(instance.shape_config, 'memory_in_gbs') else 'N/A',
                 "private_ip": "N/A", "public_ip": "N/A", "ipv6_address": "N/A",
                 "boot_volume_size_gb": "N/A", "vnic_id": None, "subnet_id": None
             }
             vnic_attachments = oci.pagination.list_call_get_all_results(compute_client.list_vnic_attachments, compartment_id=compartment_id, instance_id=instance.id).data
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

             boot_vol_attachments = oci.pagination.list_call_get_all_results(
                 compute_client.list_boot_volume_attachments, 
                 instance.availability_domain,
                 compartment_id,
                 instance_id=instance.id
             ).data
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
    instance_name = data.get('instance_name', instance_id[-12:])

    if not action or not instance_id: return jsonify({"error": "Action and instance_id are required"}), 400
    
    task_id = str(uuid.uuid4())
    db = get_db()
    db.execute('INSERT INTO tasks (id, type, name, status, result, created_at) VALUES (?, ?, ?, ?, ?, ?)', 
               (task_id, 'action', f"{action} on {instance_name}", 'pending', '', datetime.datetime.utcnow().isoformat()))
    db.commit()

    task_kwargs = { 'profile_config': g.oci_config, 'action': action, 'instance_id': instance_id, 'data': data }
    _instance_action_task.delay(task_id, **task_kwargs)
    return jsonify({"message": f"'{action}' 请求已提交...", "task_id": task_id})

@app.route('/api/create-instance', methods=['POST'])
@login_required
@oci_clients_required
def create_instance():
    task_id = str(uuid.uuid4())
    data = request.json
    db = get_db()
    alias = session.get('oci_profile_alias')
    db.execute('INSERT INTO tasks (id, type, name, status, result, created_at) VALUES (?, ?, ?, ?, ?, ?)', 
               (task_id, 'create', data.get('display_name_prefix', 'N/A'), 'pending', '', datetime.datetime.utcnow().isoformat()))
    db.commit()
    _create_instance_task.delay(task_id, g.oci_config, alias, data)
    return jsonify({"message": "创建实例请求已提交...", "task_id": task_id})

@app.route('/api/snatch-instance', methods=['POST'])
@login_required
@oci_clients_required
def snatch_instance():
    task_id = str(uuid.uuid4())
    data = request.json
    db = get_db()
    alias = session.get('oci_profile_alias')
    db.execute('INSERT INTO tasks (id, type, name, status, result, created_at) VALUES (?, ?, ?, ?, ?, ?)', 
               (task_id, 'snatch', data.get('display_name_prefix', 'N/A'), 'pending', '', datetime.datetime.utcnow().isoformat()))
    db.commit()
    _snatch_instance_task.delay(task_id, g.oci_config, alias, data)
    return jsonify({"message": "抢占实例任务已提交...", "task_id": task_id})

@app.route('/api/task_status/<task_id>')
@login_required
def task_status(task_id):
    task = query_db('SELECT * FROM tasks WHERE id = ?', [task_id], one=True)
    if task is None: return jsonify({'status': 'not_found'}), 404
    return jsonify({'status': task['status'], 'result': task['result']})

# --- Celery Tasks ---
def _db_execute(query, params=()):
    db = sqlite3.connect(DATABASE)
    db.execute(query, params)
    db.commit()
    db.close()

@celery.task
def _instance_action_task(task_id, profile_config, action, instance_id, data):
    _db_execute('UPDATE tasks SET status = ?, result = ? WHERE id = ?', ('running', '正在执行操作...', task_id))
    try:
        clients, error = get_oci_clients(profile_config)
        if error: raise Exception(error)
        
        compute_client = clients['compute']
        vnet_client = clients['vnet']
        action_upper = action.upper()
        result_message = ""

        if action_upper in ["START", "STOP", "SOFTRESET"]:
            compute_client.instance_action(instance_id=instance_id, action=action_upper)
            result_message = f"实例 {action_upper} 命令已发送。"
        elif action_upper == "TERMINATE":
            preserve = data.get('preserve_boot_volume', False)
            compute_client.terminate_instance(instance_id, preserve_boot_volume=preserve)
            result_message = "实例终止命令已发送。"
        elif action_upper == "CHANGEIP":
            vnic_id = data.get('vnic_id')
            if not vnic_id: raise Exception("缺少 VNIC ID，无法更换IP。")
            compartment_id = profile_config['tenancy']
            list_private_ips_response = oci.pagination.list_call_get_all_results(vnet_client.list_private_ips, vnic_id=vnic_id)
            primary_private_ip = next((p for p in list_private_ips_response.data if p.is_primary), None)
            if not primary_private_ip: raise Exception(f"未能在 VNIC {vnic_id} 上找到主私有 IP。")
            
            try:
                get_public_ip_details = oci.core.models.GetPublicIpByPrivateIpIdDetails(private_ip_id=primary_private_ip.id)
                existing_public_ip = vnet_client.get_public_ip_by_private_ip_id(get_public_ip_details).data
                if existing_public_ip.lifetime == oci.core.models.PublicIp.LIFETIME_EPHEMERAL:
                    vnet_client.delete_public_ip(existing_public_ip.id)
                    time.sleep(5)
            except ServiceError as e:
                if e.status != 404: raise
            
            create_public_ip_details = CreatePublicIpDetails(compartment_id=compartment_id, lifetime="EPHEMERAL", private_ip_id=primary_private_ip.id)
            new_public_ip = vnet_client.create_public_ip(create_public_ip_details).data
            result_message = f"更换IP请求成功，新IP: {new_public_ip.ip_address}"
        elif action_upper == "ASSIGNIPV6":
            vnic_id = data.get('vnic_id')
            subnet_id = data.get('subnet_id')
            if not vnic_id or not subnet_id: raise Exception("缺少 VNIC ID 或 Subnet ID，无法分配IPv6。")
            
            subnet = vnet_client.get_subnet(subnet_id).data
            if not subnet.ipv6_cidr_block: raise Exception(f"子网 {subnet.display_name} 未配置IPv6 CIDR，无法分配地址。")
            
            create_ipv6_details = CreateIpv6Details(vnic_id=vnic_id)
            new_ipv6 = vnet_client.create_ipv6(create_ipv6_details).data
            result_message = f"已成功请求IPv6地址。\n新IPv6地址: {new_ipv6.ip_address}"
        
        _db_execute('UPDATE tasks SET status = ?, result = ? WHERE id = ?', ('success', result_message, task_id))
        return result_message
    except Exception as e:
        error_message = f"操作 '{action_upper}' 失败: {str(e)}"
        _db_execute('UPDATE tasks SET status = ?, result = ? WHERE id = ?', ('failure', error_message, task_id))
        return error_message

@celery.task
def _create_instance_task(task_id, profile_config, alias, details):
    _db_execute('UPDATE tasks SET status = ?, result = ? WHERE id = ?', ('running', '正在创建实例...', task_id))
    try:
        clients, error = get_oci_clients(profile_config)
        if error: raise Exception(error)
        compute_client, identity_client, vnet_client = clients['compute'], clients['identity'], clients['vnet']
        tenancy_ocid = profile_config.get('tenancy')
        ssh_key = profile_config.get('default_ssh_public_key')
        if not ssh_key:
            raise Exception("账号配置缺少默认SSH公钥，无法创建实例。")
        
        _db_execute('UPDATE tasks SET status = ?, result = ? WHERE id = ?', ('running', '正在检查和配置网络...', task_id))
        subnet_id = _ensure_subnet_in_profile(alias, vnet_client, tenancy_ocid)
        _db_execute('UPDATE tasks SET status = ?, result = ? WHERE id = ?', ('running', f'网络准备就绪: ...{subnet_id[-12:]}', task_id))

        ads = oci.pagination.list_call_get_all_results(identity_client.list_availability_domains, compartment_id=tenancy_ocid).data
        if not ads: raise Exception("无法获取可用域")
        ad_name = ads[0].name
        
        os_name, os_version = details['os_name_version'].split('-')
        shape = details['shape']
        images = oci.pagination.list_call_get_all_results(compute_client.list_images, compartment_id=tenancy_ocid, operating_system=os_name, operating_system_version=os_version, shape=shape, sort_by="TIMECREATED", sort_order="DESC").data
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
                compartment_id=tenancy_ocid, availability_domain=ad_name, shape=shape, display_name=instance_name,
                create_vnic_details=oci.core.models.CreateVnicDetails(subnet_id=subnet_id, assign_public_ip=True),
                metadata={"ssh_authorized_keys": ssh_key, "user_data": user_data_encoded},
                source_details=oci.core.models.InstanceSourceViaImageDetails(image_id=image_ocid, boot_volume_size_in_gbs=details['boot_volume_size']),
                shape_config=oci.core.models.LaunchInstanceShapeConfigDetails(ocpus=details.get('ocpus'), memory_in_gbs=details.get('memory_in_gbs')) if "Flex" in shape else None)
            instance = compute_client.launch_instance(launch_details).data
            created_instances_info.append(instance_name)
            if i < instance_count - 1: time.sleep(3)
        
        success_message = f"🎉 {len(created_instances_info)}个实例创建成功!\n    - 实例名: {', '.join(created_instances_info)}\n    - Root 密码: {root_password} (所有实例通用)"
        _db_execute('UPDATE tasks SET status = ?, result = ? WHERE id = ?', ('success', success_message, task_id))
        return success_message
    except ServiceError as e:
        if e.status == 500 and "Out of host capacity" in e.message:
            error_message = f"❌ 实例创建失败! \n    - 原因: 容量不足，请稍后再试。"
        else:
            error_message = f"❌ 实例创建失败! \n    - OCI API 错误: {str(e)}"
        _db_execute('UPDATE tasks SET status = ?, result = ? WHERE id = ?', ('failure', error_message, task_id))
        return error_message
    except Exception as e:
        error_message = f"❌ 实例创建失败! \n    - 原因: {str(e)}"
        _db_execute('UPDATE tasks SET status = ?, result = ? WHERE id = ?', ('failure', error_message, task_id))
        return error_message


@celery.task
def _snatch_instance_task(task_id, profile_config, alias, details):
    _db_execute('UPDATE tasks SET status = ?, result = ? WHERE id = ?', ('running', '抢占任务开始...', task_id))
    try:
        clients, error = get_oci_clients(profile_config)
        if error: raise Exception(error)
        compute_client, identity_client, vnet_client = clients['compute'], clients['identity'], clients['vnet']
        tenancy_ocid = profile_config.get('tenancy')
        ssh_key = profile_config.get('default_ssh_public_key')
        if not ssh_key:
            raise Exception("账号配置缺少默认SSH公钥，无法开始抢占任务。")
        
        _db_execute('UPDATE tasks SET status = ?, result = ? WHERE id = ?', ('running', '正在检查和配置网络...', task_id))
        subnet_id = _ensure_subnet_in_profile(alias, vnet_client, tenancy_ocid)
        _db_execute('UPDATE tasks SET status = ?, result = ? WHERE id = ?', ('running', f'网络准备就绪: ...{subnet_id[-12:]}', task_id))

        ads = identity_client.list_availability_domains(compartment_id=tenancy_ocid).data
        ad_name = details.get('availabilityDomain') or ads[0].name
        
        os_name, os_version = details['os_name_version'].split('-')
        shape = details['shape']
        images = oci.pagination.list_call_get_all_results(compute_client.list_images, compartment_id=tenancy_ocid, operating_system=os_name, operating_system_version=os_version, shape=shape, sort_by="TIMECREATED", sort_order="DESC").data
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

        launch_details = oci.core.models.LaunchInstanceDetails(
            compartment_id=tenancy_ocid, availability_domain=ad_name, shape=shape,
            display_name=details.get('display_name_prefix', 'snatch-instance'),
            create_vnic_details=oci.core.models.CreateVnicDetails(subnet_id=subnet_id, assign_public_ip=True),
            metadata={"ssh_authorized_keys": ssh_key, "user_data": user_data_encoded},
            source_details=oci.core.models.InstanceSourceViaImageDetails(image_id=image_ocid, boot_volume_size_in_gbs=details['boot_volume_size']),
            shape_config=oci.core.models.LaunchInstanceShapeConfigDetails(ocpus=details.get('ocpus'), memory_in_gbs=details.get('memory_in_gbs')) if "Flex" in shape else None)
        
    except Exception as e:
        error_message = f"❌ 抢占任务准备阶段失败! \n    - 原因: {str(e)}"
        _db_execute('UPDATE tasks SET status = ?, result = ? WHERE id = ?', ('failure', error_message, task_id))
        return error_message

    retry_count = 0
    min_delay = details.get('min_delay', 30)
    max_delay = details.get('max_delay', 90)

    while True:
        retry_count += 1
        delay = random.randint(min_delay, max_delay)

        task_record = query_db('SELECT status FROM tasks WHERE id = ?', [task_id], one=True)
        if task_record is None or task_record['status'] == 'failure':
            logging.info(f"任务 {task_id} 已被外部停止，退出抢占循环。")
            return "任务已被用户手动停止。"

        try:
            _db_execute('UPDATE tasks SET status = ?, result = ? WHERE id = ?', ('running', f"第 {retry_count} 次尝试创建实例...", task_id))
            instance = compute_client.launch_instance(launch_details).data
            
            success_message = f"🎉 抢占成功 (第 {retry_count} 次尝试)!\n    - 实例名: {instance.display_name}\n    - Root 密码: {root_password}"
            _db_execute('UPDATE tasks SET status = ?, result = ? WHERE id = ?', ('success', success_message, task_id))
            return success_message

        except ServiceError as e:
            if e.status == 500 and ("OutOfCapacity" in e.code or "Out of host capacity" in e.message):
                status_msg = f"第 {retry_count} 次尝试失败：资源不足。将在 {delay} 秒后重试..."
                _db_execute('UPDATE tasks SET status = ?, result = ? WHERE id = ?', ('running', status_msg, task_id))
                time.sleep(delay)
                continue
            else:
                status_msg = f"第 {retry_count} 次尝试失败：API错误 ({e.code})。将在 {delay} 秒后重试..."
                _db_execute('UPDATE tasks SET status = ?, result = ? WHERE id = ?', ('running', status_msg, task_id))
                time.sleep(delay)
                continue
        except Exception as e:
            status_msg = f"第 {retry_count} 次尝试失败：发生未知错误。将在 {delay} 秒后重试..."
            _db_execute('UPDATE tasks SET status = ?, result = ? WHERE id = ?', ('running', status_msg, task_id))
            time.sleep(delay)
            continue

# --- Main Execution ---
init_db()
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5003, debug=False)
