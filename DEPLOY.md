
---

## 2. 编写部署文档（可选，直接复制下面内容）

在项目根目录新建一个 `DEPLOY.md` 文件，粘贴以下内容：

```markdown
# 部署文档

## 本地开发环境

1. 确保已安装 Python 3.6+ 和 pip。
2. 克隆项目并进入目录。
3. 执行 `pip install flask` 安装依赖。
4. 执行 `python app.py` 启动开发服务器。
5. 在浏览器中访问 `http://127.0.0.1:5000` 即可。

## 部署到云服务器（以 Linux 为例）

1. 登录云服务器，安装 Python 3 和 pip。
2. 克隆项目到服务器目录，例如 `/var/www/校园闲置交易平台`。
3. 安装依赖：`pip install flask gunicorn`。
4. 使用 Gunicorn 作为 WSGI 服务器启动应用：
   ```bash
   gunicorn -w 4 -b 0.0.0.0:5000 app:app
