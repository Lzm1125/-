from flask import Flask, request, jsonify, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import os
import datetime

# 初始化 Flask 应用
app = Flask(__name__)
# 配置密钥（生产环境需替换为随机字符串，用于 session/加密）
app.secret_key = 'campus_trade_2026_secret_key'
# 配置跨域（可选，供前端调用时避免跨域报错）
app.config['JSON_AS_ASCII'] = False  # 支持中文返回

# 配置 SQLite 数据库
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{os.path.join(BASE_DIR, "campus_trade.db")}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False  # 关闭不必要的修改追踪

# 初始化数据库
db = SQLAlchemy(app)

# -------------------------- 数据模型定义 --------------------------
# 用户模型
class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    username = db.Column(db.String(50), unique=True, nullable=False, comment='用户名')
    email = db.Column(db.String(120), unique=True, nullable=False, comment='邮箱')
    password_hash = db.Column(db.String(256), nullable=False, comment='加密密码')
    create_time = db.Column(db.DateTime, default=datetime.datetime.utcnow, comment='注册时间')
    # 关联商品（一对多：一个用户可发布多个商品）
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

# 商品模型
class Item(db.Model):
    __tablename__ = 'items'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    title = db.Column(db.String(100), nullable=False, comment='商品标题')
    description = db.Column(db.Text, nullable=False, comment='商品描述')
    price = db.Column(db.Float, nullable=False, comment='商品价格')
    category = db.Column(db.String(50), nullable=False, comment='商品分类：书籍/电子产品/生活用品/其他')
    publish_time = db.Column(db.DateTime, default=datetime.datetime.utcnow, comment='发布时间')
    # 外键：关联用户ID
    seller_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, comment='发布者ID')

    # 转字典（供接口返回JSON）
    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'description': self.description,
            'price': round(self.price, 2),
            'category': self.category,
            'publish_time': self.publish_time.strftime('%Y-%m-%d %H:%M:%S'),
            'seller_id': self.seller_id,
            'seller_name': self.seller.username  # 关联查询发布者用户名
        }

# 初始化数据库表（启动时自动创建）
with app.app_context():
    db.create_all()
    print(f"数据库初始化完成，文件路径：{os.path.join(BASE_DIR, 'campus_trade.db')}")

# -------------------------- 核心接口定义 --------------------------
# 1. 用户注册接口
@app.route('/api/register', methods=['POST'])
def register():
    """
    用户注册接口
    请求参数（JSON）：
    {
        "username": "张三",
        "email": "zhangsan@test.com",
        "password": "123456"
    }
    返回：JSON 结果
    """
    # 获取请求参数
    data = request.get_json()
    if not data or not all(key in data for key in ['username', 'email', 'password']):
        return jsonify({'code': 400, 'msg': '参数不全，请提供用户名、邮箱、密码'}), 400
    
    # 检查用户名/邮箱是否已存在
    if User.query.filter_by(username=data['username']).first():
        return jsonify({'code': 400, 'msg': '用户名已存在'}), 400
    if User.query.filter_by(email=data['email']).first():
        return jsonify({'code': 400, 'msg': '邮箱已被注册'}), 400
    
    # 创建用户（密码加密）
    user = User(username=data['username'], email=data['email'])
    user.set_password(data['password'])
    db.session.add(user)
    db.session.commit()
    
    return jsonify({'code': 200, 'msg': '注册成功', 'data': user.to_dict()}), 200

# 2. 用户登录接口
@app.route('/api/login', methods=['POST'])
def login():
    """
    用户登录接口
    请求参数（JSON）：
    {
        "username": "张三",
        "password": "123456"
    }
    返回：JSON 结果（包含登录态）
    """
    data = request.get_json()
    if not data or not all(key in data for key in ['username', 'password']):
        return jsonify({'code': 400, 'msg': '参数不全，请提供用户名和密码'}), 400
    
    # 验证用户
    user = User.query.filter_by(username=data['username']).first()
    if not user or not user.check_password(data['password']):
        return jsonify({'code': 401, 'msg': '用户名或密码错误'}), 401
    
    # 记录登录态（session）
    session['user_id'] = user.id
    session['username'] = user.username
    
    return jsonify({
        'code': 200,
        'msg': '登录成功',
        'data': {'user': user.to_dict(), 'login_state': True}
    }), 200

# 3. 用户登出接口
@app.route('/api/logout', methods=['POST'])
def logout():
    """用户登出接口（清除登录态）"""
    session.clear()
    return jsonify({'code': 200, 'msg': '登出成功'}), 200

# 4. 发布商品接口（需登录）
@app.route('/api/items', methods=['POST'])
def publish_item():
    """
    发布商品接口（需登录）
    请求参数（JSON）：
    {
        "title": "二手Python编程书",
        "description": "9成新，附带笔记",
        "price": 29.9,
        "category": "书籍"
    }
    返回：JSON 结果
    """
    # 检查登录态
    if 'user_id' not in session:
        return jsonify({'code': 401, 'msg': '请先登录'}), 401
    
    # 获取请求参数
    data = request.get_json()
    required_keys = ['title', 'description', 'price', 'category']
    if not data or not all(key in data for key in required_keys):
        return jsonify({'code': 400, 'msg': '参数不全，请提供商品标题、描述、价格、分类'}), 400
    
    # 验证价格
    try:
        price = float(data['price'])
        if price <= 0:
            return jsonify({'code': 400, 'msg': '价格必须大于0'}), 400
    except:
        return jsonify({'code': 400, 'msg': '价格必须是数字'}), 400
    
    # 创建商品
    item = Item(
        title=data['title'],
        description=data['description'],
        price=price,
        category=data['category'],
        seller_id=session['user_id']
    )
    db.session.add(item)
    db.session.commit()
    
    return jsonify({'code': 200, 'msg': '商品发布成功', 'data': item.to_dict()}), 200

# 5. 获取所有商品列表接口
@app.route('/api/items', methods=['GET'])
def get_all_items():
    """获取所有商品列表接口（无需登录）"""
    items = Item.query.all()
    item_list = [item.to_dict() for item in items]
    return jsonify({
        'code': 200,
        'msg': '获取成功',
        'data': {'total': len(item_list), 'items': item_list}
    }), 200

# 6. 获取单个商品详情接口
@app.route('/api/items/<int:item_id>', methods=['GET'])
def get_item_detail(item_id):
    """获取单个商品详情接口（无需登录）"""
    item = Item.query.get(item_id)
    if not item:
        return jsonify({'code': 404, 'msg': '商品不存在'}), 404
    return jsonify({'code': 200, 'msg': '获取成功', 'data': item.to_dict()}), 200

# 7. 删除商品接口（仅发布者可删）
@app.route('/api/items/<int:item_id>', methods=['DELETE'])
def delete_item(item_id):
    """删除商品接口（需登录且为发布者）"""
    if 'user_id' not in session:
        return jsonify({'code': 401, 'msg': '请先登录'}), 401
    
    item = Item.query.get(item_id)
    if not item:
        return jsonify({'code': 404, 'msg': '商品不存在'}), 404
    
    # 验证是否为发布者
    if item.seller_id != session['user_id']:
        return jsonify({'code': 403, 'msg': '无权限删除该商品'}), 403
    
    db.session.delete(item)
    db.session.commit()
    return jsonify({'code': 200, 'msg': '商品删除成功'}), 200

# 启动服务
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)