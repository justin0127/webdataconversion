# app.py - 后端服务
from flask import Flask, render_template, request, jsonify, redirect, url_for, send_file
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash  # 添加这一行
import os
import yaml
import pandas as pd
import numpy as np
import uuid
import shutil
import logging
from datetime import datetime
from typing import Dict, List, Any, Optional

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 初始化Flask应用
app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///clients.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = 'your-secret-key-here'  # 设置一个随机字符串作为密钥

# 初始化Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# 初始化数据库
db = SQLAlchemy(app)

# 用户模型
class User(UserMixin, db.Model):
    id = db.Column(db.String(50), primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)



# 全局上下文处理器
@app.context_processor
def inject_now():
    """向所有模板注入当前时间"""
    return {'now': datetime.now()}

# 定义数据模型
class Client(db.Model):
    id = db.Column(db.String(50), primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    yaml_file = db.Column(db.String(200))
    template_file = db.Column(db.String(200))
    # 添加与ConversionTask的关系，设置级联删除
    tasks = db.relationship('ConversionTask', backref='client', lazy=True, cascade="all, delete-orphan")

class ConversionTask(db.Model):
    id = db.Column(db.String(50), primary_key=True)
    client_id = db.Column(db.String(50), db.ForeignKey('client.id'), nullable=False)
    source_file = db.Column(db.String(200), nullable=False)
    result_file = db.Column(db.String(200))
    status = db.Column(db.String(20), default='pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# 确保上传文件夹存在
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'clients'), exist_ok=True)
os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'sources'), exist_ok=True)
os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'results'), exist_ok=True)

def _load_config( config_path: str) -> Dict[str, Any]:
        """加载配置文件"""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.error(f"加载配置文件失败: {e}")
            raise
        
def _process_config_variables(config):
    """处理配置中的变量引用"""
    variables = {
        key: value 
        for key, value in config.items() 
        if key not in ['source_file', 'target_template', 'output_file', 'mappings']
    }
    # 处理output_file中的${变量名}语法
    output_file = config.get('output_file', '')
    if output_file:
        import re
        # 使用正则表达式查找并替换所有${变量名}
        output_file = re.sub(
            r'\$\{(\w+)\}', 
            lambda match: str(variables.get(match.group(1), match.group(0))), 
            output_file
        )
        config['output_file'] = output_file
    return config    

def _execute_formula( formula: str, row: pd.Series) -> Any:
    """执行自定义公式"""
    try:
        # 创建包含row对象的局部变量字典
        local_vars = {'row': row}
        
        # 添加常用的Python函数和模块
        local_vars.update({
            'sum': sum, 'len': len, 'max': max, 'min': min, 
            'round': round, 'str': str, 'int': int, 'float': float,
            'np': np, 'pd': pd
        })
        
        # 执行公式
        logger.debug(f"执行公式: {formula}, 行数据: {row.to_dict()}")
        return eval(formula, {}, local_vars)
    except Exception as e:
        logger.warning(f"公式执行错误: {formula}, 错误: {e}")
        return None
                
# 数据转换功能
def transform_data(client_id, source_file_path, yaml_file_path, template_file_path):
    try:
        client = Client.query.get(client_id)
        result_file = os.path.join(
            app.config['UPLOAD_FOLDER'], 
            'results', 
            f"result_{client.name+'_'+uuid.uuid4().hex[:8]}.xlsx"
        )
        
        # 读取源文件
        logger.info(f"读取源文件: {source_file_path}")
        source_df = pd.read_excel(source_file_path)
        #读取模板文件
        logger.info(f"读取目标模板: {template_file_path}")
        template_df = pd.read_excel(template_file_path)
        
        logger.info(f"读取yamlconfig: {yaml_file_path}")
        yamlconfig = _process_config_variables(_load_config(yaml_file_path))
        # 这里应实现实际的转换逻辑
        logger.info("开始数据转换...")
        output_df = template_df.copy()
        # 处理每一行数据
        for _, source_row in source_df.iterrows():
            # 创建新的输出行，初始化为NaN
            output_row = pd.Series(index=output_df.columns, dtype=object)
            
            # 应用映射规则
            for mapping in yamlconfig.get('mappings', []):
                target_column = mapping.get('target')
                source_columns = mapping.get('source')
                mapping_type = mapping.get('type', 'direct')
                formula = mapping.get('formula')
                
                if not target_column or not source_columns:
                    logger.warning("映射配置不完整，跳过")
                    continue
                
                if mapping_type == 'direct':
                    # 直接映射 (单列1-1对应)
                    if isinstance(source_columns, str):
                        source_columns = [source_columns]
                    if len(source_columns) == 1:
                        output_row[target_column] = source_row.get(source_columns[0])
                    else:
                        logger.warning("直接映射需要单个源列")
                
                elif mapping_type == 'formula':
                    # 公式映射
                    if formula:
                        output_row[target_column] = _execute_formula(formula, source_row)
                    else:
                        logger.warning("公式映射需要定义公式")
                
                elif mapping_type == 'combine':
                    # 多列合并
                    separator = mapping.get('separator', '')
                    values = [str(source_row.get(col, '')) for col in source_columns if col in source_row]
                    output_row[target_column] = separator.join(values)
            
            # 添加到输出DataFrame
            output_df = pd.concat([output_df, pd.DataFrame([output_row])], ignore_index=True)
        
        # 保存结果
        logger.info(f"保存转换结果到: {result_file}")
        output_df.to_excel(result_file, index=False)
        #自动调整列宽
        #._adjust_column_widths(yamlconfig.output_file)
        logger.info("数据转换完成!")
            
        return result_file
    except Exception as e:
        logger.error(f"数据转换错误: {e}")
        return None

# 用户加载回调
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(user_id)

# 登录路由
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):  # 验证密码
            login_user(user)
            return redirect(url_for('index'))
        else:
            return render_template('login.html', error='用户名或密码错误')
    return render_template('login.html')

# 注销路由
@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# 路由定义
@app.route('/')
@login_required
def index():
    clients = Client.query.all()
    return render_template('index.html', clients=clients)

@app.route('/client/create', methods=['GET', 'POST'])
@login_required
def create_client():
    if request.method == 'POST':
        client_name = request.form.get('client_name')
        if not client_name:
            return jsonify({"error": "客户名称不能为空"}), 400
        
        # 生成唯一ID
        client_id = str(uuid.uuid4())
        
        # 处理YAML文件上传
        yaml_file = request.files.get('yaml_file')
        template_file = request.files.get('template_file')
        
        yaml_path = None
        template_path = None
        
        if yaml_file:
            filename = secure_filename(yaml_file.filename)
            yaml_path = os.path.join(app.config['UPLOAD_FOLDER'], 'clients', f"{client_id}_config.yaml")
            yaml_file.save(yaml_path)
        
        if template_file:
            filename = secure_filename(template_file.filename)
            template_path = os.path.join(app.config['UPLOAD_FOLDER'], 'clients', f"{client_id}_template.xlsx")
            template_file.save(template_path)
        
        # 保存客户信息
        new_client = Client(
            id=client_id,
            name=client_name,
            yaml_file=yaml_path,
            template_file=template_path
        )
        
        db.session.add(new_client)
        db.session.commit()
        
        return redirect(url_for('index'))
    
    return render_template('create_client.html')

@app.route('/static/<path:path>')
@login_required
def send_static(path):
    return send_from_directory('static', path)

@app.route('/client/<client_id>/transform', methods=['GET', 'POST'])
@login_required
def transform_data_page(client_id):
    client = Client.query.get(client_id)
    if not client:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        source_file = request.files.get('source_file')
        print("sourcefile", source_file.filename)
        # 检查文件是否存在且文件名不为空
        if not source_file or source_file.filename == '':
            return jsonify({"error": "请上传源文件"}), 400
        
        # 保存源文件
        filename = secure_filename(source_file.filename)
        source_path = os.path.join(app.config['UPLOAD_FOLDER'], 'sources', filename)
        source_file.save(source_path)
        
        # 创建转换任务
        task_id = str(uuid.uuid4())
        task = ConversionTask(
            id=task_id,
            client_id=client_id,
            source_file=source_path
        )
        db.session.add(task)
        db.session.commit()
        
        # 执行转换
        result_file = transform_data(
            client_id, 
            source_path, 
            client.yaml_file, 
            client.template_file
        )
        
        # 更新任务状态
        if result_file:
            task.result_file = result_file
            task.status = 'completed'
        else:
            task.status = 'failed'
        
        db.session.commit()
        
        return redirect(url_for('task_result', task_id=task_id))
    
    return render_template('transform.html', client=client)

@app.route('/task/<task_id>/result')
@login_required
def task_result(task_id):
    task = ConversionTask.query.get(task_id)
    if not task:
        return redirect(url_for('index'))
    
    client = task.client
    return render_template('task_result.html', task=task, client=client)

@app.route('/download/<path:file_path>')
@login_required
def download_file(file_path):
    return send_file(file_path, as_attachment=True)

@app.route('/client/<client_id>/update', methods=['GET', 'POST'])
@login_required
def update_client(client_id):
    client = Client.query.get(client_id)
    if not client:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        client_name = request.form.get('client_name')
        if not client_name:
            return jsonify({"error": "客户名称不能为空"}), 400
        
        client.name = client_name
        
        # 处理YAML文件上传
        yaml_file = request.files.get('yaml_file')
        template_file = request.files.get('template_file')
        
        if yaml_file:
            filename = secure_filename(yaml_file.filename)
            yaml_path = os.path.join(app.config['UPLOAD_FOLDER'], 'clients', f"{client_id}_config.yaml")
            yaml_file.save(yaml_path)
            client.yaml_file = yaml_path
        
        if template_file:
            filename = secure_filename(template_file.filename)
            template_path = os.path.join(app.config['UPLOAD_FOLDER'], 'clients', f"{client_id}_template.xlsx")
            template_file.save(template_path)
            client.template_file = template_path
        
        # 保存更新后的客户信息
        db.session.commit()
        
        return redirect(url_for('index'))
    
    return render_template('update_client.html', client=client)

@app.route('/client/<client_id>/delete', methods=['GET'])
@login_required
def delete_client(client_id):
    client = Client.query.get(client_id)
    if client:
        # 删除相关文件
        if client.yaml_file and os.path.exists(client.yaml_file):
            os.remove(client.yaml_file)
        if client.template_file and os.path.exists(client.template_file):
            os.remove(client.template_file)
        # 从数据库中删除记录
        db.session.delete(client)
        db.session.commit()
    return redirect(url_for('index'))

def init_default_user():
    """初始化默认用户"""
    if User.query.count() == 0:
        default_username = 'admin'
        default_password = 'admin123'  # 请在生产环境中修改此密码
        
        # 生成唯一ID
        user_id = str(uuid.uuid4())
        
        # 创建默认用户
        user = User(
            id=user_id,
            username=default_username,
            password=generate_password_hash(default_password)  # 加密密码
        )
        
        db.session.add(user)
        db.session.commit()
        logger.info(f"创建默认用户: {default_username}")

# 初始化数据库
with app.app_context():
    db.create_all()    
    init_default_user()  # 调用初始化函数

if __name__ == '__main__':
    app.run(debug=True, port=5000)