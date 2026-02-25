from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
# 新增：文件上传相关依赖
from werkzeug.utils import secure_filename
import os
import datetime

# 初始化 Flask 应用
app = Flask(__name__)
app.secret_key = 'campus_trade_2026_secret_key'
app.config['JSON_AS_ASCII'] = False
app.config['REMEMBER_COOKIE_DURATION'] = datetime.timedelta(days=7)

# 配置 SQLite 数据库
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{os.path.join(BASE_DIR, "campus_trade.db")}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# -------------------------- 新增：文件上传核心配置 --------------------------
# 允许的上传文件类型
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
# 上传文件保存目录（自动创建 static/uploads）
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
# 最大上传文件大小：10MB
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024

# 自动创建上传目录
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# 初始化数据库和 Flask-Login
db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# -------------------------- 数据模型（新增图片字段）--------------------------
class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    create_time = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    items = db.relationship('Item', backref='seller', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password, method='pbkdf2:sha256')
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'create_time': self.create_time.strftime('%Y-%m-%d %H:%M:%S')
        }

class Item(db.Model):
    __tablename__ = 'items'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    title = db.Column(db.String(100), nullable=False, comment='商品名称')
    description = db.Column(db.Text, nullable=False, comment='商品描述')
    price = db.Column(db.Float, nullable=False, comment='商品价格')
    category = db.Column(db.String(50), nullable=False, comment='商品分类')
    publish_time = db.Column(db.DateTime, default=datetime.datetime.utcnow, comment='发布时间')
    seller_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, comment='发布者ID')
    # 新增：商品图片路径字段
    image_path = db.Column(db.String(256), comment='商品图片保存路径')

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'description': self.description,
            'price': round(self.price, 2),
            'category': self.category,
            'publish_time': self.publish_time.strftime('%Y-%m-%d %H:%M:%S'),
            'seller_id': self.seller_id,
            'seller_name': self.seller.username,
            'image_path': self.image_path  # 返回图片路径
        }

# Flask-Login 核心回调
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# -------------------------- 工具函数：校验文件类型 --------------------------
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# -------------------------- 核心接口（新增商品发布接口）--------------------------
# 1. 用户注册/登录/登出（保留原有功能）
@app.route('/api/register', methods=['POST'])
def register():
    data = request.get_json()
    if not data or not all(key in data for key in ['username', 'email', 'password']):
        return jsonify({'code': 400, 'msg': '参数不全'}), 400
    if User.query.filter_by(username=data['username']).first():
        return jsonify({'code': 400, 'msg': '用户名已存在'}), 400
    user = User(username=data['username'], email=data['email'])
    user.set_password(data['password'])
    db.session.add(user)
    db.session.commit()
    return jsonify({'code': 200, 'msg': '注册成功', 'data': user.to_dict()}), 200

@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    if not data or not all(key in data for key in ['username', 'password']):
        return jsonify({'code': 400, 'msg': '参数不全'}), 400
    user = User.query.filter_by(username=data['username']).first()
    if not user or not user.check_password(data['password']):
        return jsonify({'code': 401, 'msg': '用户名或密码错误'}), 401
    remember = data.get('remember', False)
    login_user(user, remember=remember)
    return jsonify({
        'code': 200,
        'msg': '登录成功',
        'data': {'user': user.to_dict(), 'is_authenticated': current_user.is_authenticated}
    }), 200

@app.route('/api/logout', methods=['POST'])
@login_required
def logout():
    logout_user()
    return jsonify({'code': 200, 'msg': '登出成功'}), 200

# 2. 核心任务：商品发布接口（/api/item/publish，支持图片上传+登录校验）
@app.route('/api/item/publish', methods=['POST'])
@login_required  # 强制校验登录态，未登录直接返回401
def publish_item():
    """
    商品发布接口（支持图片上传）
    请求方式：multipart/form-data
    请求参数：title、description、price、category、image（文件）
    """
    # 1. 获取表单参数（非文件）
    title = request.form.get('title')
    description = request.form.get('description')
    price = request.form.get('price')
    category = request.form.get('category')
    
    # 校验基础参数
    required_params = [title, description, price, category]
    if not all(required_params):
        return jsonify({'code': 400, 'msg': '参数不全：需提供商品名称、描述、价格、分类'}), 400
    
    # 校验价格格式
    try:
        price = float(price)
        if price <= 0:
            return jsonify({'code': 400, 'msg': '价格必须大于0'}), 400
    except:
        return jsonify({'code': 400, 'msg': '价格必须是数字'}), 400

    # 2. 处理图片上传
    image_path = None
    if 'image' in request.files:
        file = request.files['image']
        # 校验文件是否合法
        if file.filename == '':
            return jsonify({'code': 400, 'msg': '图片文件不能为空'}), 400
        if file and allowed_file(file.filename):
            # 生成安全的文件名（避免重名）
            filename = secure_filename(f"{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}_{file.filename}")
            # 拼接保存路径
            image_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            # 保存文件
            file.save(image_path)
            # 转换为相对路径（供前端访问）
            image_path = f"/static/uploads/{filename}"
        else:
            return jsonify({'code': 400, 'msg': '不支持的图片格式：仅支持 png/jpg/jpeg/gif'}), 400

    # 3. 创建商品记录
    item = Item(
        title=title,
        description=description,
        price=price,
        category=category,
        seller_id=current_user.id,
        image_path=image_path
    )
    db.session.add(item)
    db.session.commit()

    return jsonify({
        'code': 200,
        'msg': '商品发布成功（含图片上传）',
        'data': item.to_dict()
    }), 200

# 3. 商品查询接口（支持查看图片路径）
@app.route('/api/items', methods=['GET'])
def get_all_items():
    items = Item.query.all()
    item_list = [item.to_dict() for item in items]
    return jsonify({
        'code': 200,
        'msg': '获取成功',
        'data': {'total': len(item_list), 'items': item_list}
    }), 200

# ====================== 新增：商品列表 + 商品详情接口 ======================
# 4. 商品列表接口：/api/item/list
@app.route('/api/item/list', methods=['GET'])
def get_item_list():
    """获取所有商品列表，返回JSON格式"""
    items = Item.query.all()
    item_list = [item.to_dict() for item in items]
    return jsonify({
        'code': 200,
        'msg': '获取商品列表成功',
        'data': {
            'total': len(item_list),
            'items': item_list
        }
    }), 200

# 5. 商品详情接口：/api/item/detail/<id>
@app.route('/api/item/detail/<int:item_id>', methods=['GET'])
def get_item_detail(item_id):
    """获取单个商品详情，返回JSON格式"""
    item = Item.query.get(item_id)
    if not item:
        return jsonify({'code': 404, 'msg': '商品不存在'}), 404
    return jsonify({
        'code': 200,
        'msg': '获取商品详情成功',
        'data': item.to_dict()
    }), 200
# ====================== 商品列表 + 商品详情接口结束 ======================

# ====================== 新增：用户个人中心接口 ======================
# 6. 获取当前登录用户信息：/api/user/profile
@app.route('/api/user/profile', methods=['GET'])
@login_required  # 必须登录才能访问
def get_user_profile():
    return jsonify({
        'code': 200,
        'msg': '获取用户信息成功',
        'data': current_user.to_dict()
    }), 200

# 7. 获取当前用户发布的商品列表：/api/user/items
@app.route('/api/user/items', methods=['GET'])
@login_required  # 必须登录才能访问
def get_user_items():
    # 查询当前用户发布的所有商品
    user_items = Item.query.filter_by(seller_id=current_user.id).all()
    item_list = [item.to_dict() for item in user_items]
    return jsonify({
        'code': 200,
        'msg': '获取用户商品列表成功',
        'data': {
            'total': len(item_list),
            'items': item_list
        }
    }), 200
# ====================== 用户个人中心接口结束 ======================

# 初始化数据库
with app.app_context():
    db.create_all()
    print(f"数据库初始化完成，上传目录：{UPLOAD_FOLDER}")

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)