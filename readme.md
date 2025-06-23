data_converter/
│
├── app.py                  # 主应用入口
├── models.py               # 数据模型定义
├── converter.py            # 数据转换逻辑
├── requirements.txt        # 依赖列表
├── config.py               # 配置文件
│
├── static/                 # 静态资源
│   ├── css/                # CSS样式
│   ├── js/                 # JavaScript文件
│   └── images/             # 图片资源
│
├── templates/              # HTML模板
│   ├── index.html          # 首页
│   ├── create_client.html  # 创建客户页面
│   ├── transform.html      # 数据转换页面
│   ├── task_result.html    # 任务结果页面
│   └── layout.html         # 布局模板
│
├── uploads/                # 上传文件存储
│   ├── clients/            # 客户配置文件
│   ├── sources/            # 源数据文件
│   └── results/            # 结果文件
│
├── migrations/             # 数据库迁移
│   └── versions/
│
├── docs/                   # 文档
│   ├── architecture.md     # 架构说明
│   └── usage.md            # 使用指南
│
├── tests/                  # 测试
│   ├── unit/               # 单元测试
│   └── integration/        # 集成测试
│
├── .gitignore              # Git忽略文件
├── README.md               # 项目说明
└── LICENSE                 # 许可证