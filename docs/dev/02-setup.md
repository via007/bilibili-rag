# 开发环境

---

## 环境要求

- Python 3.10+
- Node.js 18+
- ffmpeg

---

## 本地开发

```bash
# 后端
python -m uvicorn app.main:app --reload --port 8000

# 前端
cd frontend && npm run dev
```

---

## API 文档

- Swagger: http://localhost:8000/docs
- OpenAPI: http://localhost:8000/openapi.json
