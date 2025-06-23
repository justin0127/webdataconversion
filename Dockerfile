# 使用Python官方镜像作为基础镜像
FROM python:3.9-slim

# 设置工作目录
WORKDIR /app

# 复制依赖文件
COPY requirements.txt .

# 安装依赖
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY . .

# 设置环境变量
ENV FLASK_APP=app.py
ENV FLASK_ENV=production
ENV SECRET_KEY=your-secret-key-here  # 建议在运行时通过环境变量覆盖

# 暴露应用端口
EXPOSE 5000

# 启动应用
CMD ["flask", "run", "--host=0.0.0.0", "--port=5000"]