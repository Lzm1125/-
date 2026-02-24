from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import os
import datetime

# 初始化 Flask 应用
app = Flask(__name__)
app.secret_key = 'campus_trade_2026_secret_key'  # 生产环境需替换为随机字符串
app.config['JSON_AS_ASCII'] = False  # 支持中文返回
app.config['REMEMBER_COOKIE_DURATION'] = datetime.timedelta(days=7)  # 记住我 7 天

# 配置 SQLite 数据库
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{os.path.join(BASE_DIR, "campus_trade.db")}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# 初始化数据库
db = SQLAlchemy(app)

# 初始化 Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'  # 未登录时重定向的接口

# -------------------------- 数据模型定义（集成 UserMixin）--------------------------
class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    username = db.Column(db.String(50), unique=True, nullable=False, comment='用户名')
    email = db.Column(db.String(120), unique=True, nullable=False, comment='邮箱')
    password_hash = db.Column(db.String(256), nullable=False, comment='加密密码')
    create_time = db.Column(db.DateTime, default=datetime.datetime.utcnow, comment='注册时间')
    items = db.relationship('Item', backref='seller', lazy=True)

    # 密码加密
    def set_password(self, password):
        self.password_hash = generate_password_hash(password, method='pbkdf2:sha256')
    
    # 密码验证
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    # 转字典（供接口返回JSON）
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
    title = db.Column(db.String(100), nullable=False, comment='商品标题')
    description = db.Column(db.Text, nullable=False, comment='商品描述')
    price = db.Column(db.Float, nullable=False, comment='商品价格')
    category = db.Column(db.String(50), nullable=False, comment='商品分类')
    publish_time = db.Column(db.DateTime, default=datetime.datetime.utcnow, comment='发布时间')
    seller_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, comment='发布者ID')

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'description': self.description,
            'price': round(self.price, 2),
            'category': self.category,
            'publish_time': self.publish_time.strftime('%Y-%m-%d %H:%M:%S'),
            'seller_id': self.seller_id,
            'seller_name': self.seller.username
        }

# Flask-Login 核心回调：通过用户ID加载用户
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# -------------------------- 核心接口（集成 Flask-Login）--------------------------
# 1. 用户注册接口
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

# 2. 用户登录接口（核心：Flask-Login 实现会话管理）
@app.route('/api/login', methods=['POST'])
def login():
    """
    登录接口（支持用户名+密码，Flask-Login 管理会话）
    请求参数：{"username": "xxx", "password": "xxx", "remember": true}
    """
    data = request.get_json()
    if not data or not all(key in data for key in ['username', 'password']):
        return jsonify({'code': 400, 'msg': '参数不全（需用户名、密码）'}), 400
    
    user = User.query.filter_by(username=data['username']).first()
    if not user or not user.check_password(data['password']):
        return jsonify({'code': 401, 'msg': '用户名或密码错误'}), 401
    
    # 登录并保持会话：remember=True 实现“记住我”
    remember = data.get('remember', False)
    login_user(user, remember=remember)
    
    return jsonify({
        'code': 200,
        'msg': '登录成功',
        'data': {
            'user': user.to_dict(),
            'is_authenticated': current_user.is_authenticated  # 登录状态标识
        }
    }), 200

# 3. 登出接口（Flask-Login 清除会话）
@app.route('/api/logout', methods=['POST'])
@login_required  # 必须登录才能访问
def logout():
    logout_user()
    return jsonify({'code': 200, 'msg': '登出成功'}), 200

# 4. 测试接口：验证登录状态（可作为测试用例）
@app.route('/api/user/info', methods=['GET'])
@login_required  # 未登录会返回 401
def get_user_info():
    return jsonify({
        'code': 200,
        'msg': '获取用户信息成功',
        'data': current_user.to_dict()
    }), 200

# 5. 发布商品接口（已集成登录校验）
@app.route('/api/items', methods=['POST'])
@login_required
def publish_item():
    data = request.get_json()
    required_keys = ['title', 'description', 'price', 'category']
    if not data or not all(key in data for key in required_keys):
        return jsonify({'code': 400, 'msg': '参数不全'}), 400
    try:
        price = float(data['price'])
        if price <= 0:
            return jsonify({'code': 400, 'msg': '价格必须大于0'}), 400
    except:
        return jsonify({'code': 400, 'msg': '价格必须是数字'}), 400
    item = Item(
        title=data['title'],
        description=data['description'],
        price=price,
        category=data['category'],
        seller_id=current_user.id  # 直接获取当前登录用户ID
    )
    db.session.add(item)
    db.session.commit()
    return jsonify({'code': 200, 'msg': '商品发布成功', 'data': item.to_dict()}), 200

# 6. 商品查询接口（无需登录）
@app.route('/api/items', methods=['GET'])
def get_all_items():
    items = Item.query.all()
    item_list = [item.to_dict() for item in items]
    return jsonify({'code': 200, 'msg': '获取成功', 'data': {'total': len(item_list), 'items': item_list}}), 200

# 初始化数据库
with app.app_context():
    db.create_all()
    print(f"数据库初始化完成：{os.path.join(BASE_DIR, 'campus_trade.db')}")

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)