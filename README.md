# 股票投资仪表盘 (Stock Investment Dashboard)

全栈股票自选股监控仪表盘，支持 A股 / 港股 / 美股实时行情。

## 技术栈

**后端**: Python FastAPI + SQLAlchemy + SQLite + akshare  
**前端**: Vue 3 + Vite + Pinia + Vue Router + Axios  
**数据源**: akshare（东方财富接口）

## 项目结构

```
stock-dashboard/
├── backend/                    # FastAPI 后端
│   ├── main.py                 # 应用入口，CORS，静态文件服务
│   ├── database.py             # SQLite 数据库连接
│   ├── models.py               # ORM 模型（User, WatchlistItem）
│   ├── schemas.py              # Pydantic 请求/响应模型
│   ├── routes/
│   │   ├── auth.py             # 认证接口（登录/注册/JWT）
│   │   └── stocks.py           # 自选股 CRUD + 数据刷新
│   ├── services/
│   │   └── stock_service.py    # akshare 数据服务（带缓存）
│   └── requirements.txt        # Python 依赖
├── frontend/                   # Vue 3 前端
│   ├── index.html
│   ├── package.json
│   ├── vite.config.js
│   └── src/
│       ├── main.js
│       ├── App.vue
│       ├── assets/main.css     # 全局样式（深色主题）
│       ├── api/index.js        # Axios 封装 + 请求拦截器
│       ├── router/index.js     # 路由（Login / Dashboard）
│       ├── stores/
│       │   ├── authStore.js    # 认证状态（Pinia）
│       │   └── stockStore.js   # 自选股状态（Pinia）
│       ├── views/
│       │   ├── Login.vue       # 登录/注册页
│       │   └── Dashboard.vue   # 主仪表盘
│       └── components/
│           ├── StockCard.vue   # 股票卡片（行情/新闻/笔记）
│           └── AddStockModal.vue # 添加自选股弹窗
└── README.md
```

## 快速启动

### 1. 后端启动

```bash
cd backend
pip install -r requirements.txt
python main.py
```

后端将在 http://localhost:8000 启动，API 文档访问 http://localhost:8000/docs

### 2. 前端启动（开发模式）

```bash
cd frontend
npm install
npm run dev
```

前端将在 http://localhost:5173 启动，自动代理 API 请求到后端。

### 3. 构建前端（生产模式）

```bash
cd frontend
npm run build
```

构建后前端文件输出到 `frontend/dist/`，后端会自动挂载为静态文件。

**注意**: 必须先启动后端，前端才能正常获取数据。

## 功能说明

### 用户系统
- 首次使用需要注册账号
- JWT Token 认证，自动续期

### 自选股管理
- 支持 A股（如 600519）、港股（如 00700）、美股（如 AAPL）
- 添加自选股时支持实时搜索匹配
- 删除自选股（鼠标悬停显示删除按钮）

### 行情展示
- 实时价格、涨跌额、涨跌幅
- 昨收价、最高价、最低价
- 振幅、换手率、市盈率、成交量
- 30 日迷你走势图（sparkline）
- 涨/跌/平颜色区分（绿涨红跌）

### 市场分类
- 全部 / A股 / 港股 / 美股 分类查看
- 每个分类显示股票数量

### 资讯与笔记
- 每只股票最新 3 条新闻（点击跳转）
- 研究笔记（自动保存到数据库）

### 自动刷新
- 首次加载时刷新全部数据
- 每 30 秒自动刷新
- 手动刷新按钮
- 30 秒内存缓存，避免重复请求

## API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /api/auth/register | 注册 |
| POST | /api/auth/login | 登录 |
| GET | /api/auth/me | 当前用户信息 |
| GET | /api/stocks/list | 自选股列表 |
| POST | /api/stocks/add | 添加自选股 |
| PUT | /api/stocks/notes/{id} | 更新笔记 |
| DELETE | /api/stocks/remove/{id} | 删除自选股 |
| POST | /api/stocks/refresh | 批量刷新行情数据 |
| GET | /api/stocks/search?keyword= | 搜索股票 |
| GET | /api/health | 健康检查 |

## 数据说明

数据来源于 akshare（东方财富），属于 A 股/港股/美股行情数据。  
行情数据约 3-5 秒延迟，适合日常监控，不适合高频交易。  
内存缓存 TTL 为 30 秒，降低重复请求频率。
