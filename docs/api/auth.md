# 认证 API

> 用户登录、登出相关接口

---

## 目录

- [获取二维码](#获取二维码)
- [轮询登录状态](#轮询登录状态)
- [获取用户会话](#获取用户会话)
- [删除用户会话](#删除用户会话)

---

## 获取二维码

### GET /auth/qrcode

获取登录二维码

**响应**
```json
{
  "url": "https://login.bilibili.com/qrcode/h5/xxxx",
  "qrcode_key": "xxxxx"
}
```

---

## 轮询登录状态

### GET /auth/qrcode/poll/{qrcode_key}

轮询二维码扫描状态

**响应 - 已扫码未确认**
```json
{
  "status": "scanned",
  "message": "请在手机上确认"
}
```

**响应 - 登录成功**
```json
{
  "status": "confirmed",
  "message": "登录成功",
  "session_id": "xxxxx",
  "cookie": "xxxxx"
}
```

**响应 - 已过期**
```json
{
  "status": "expired",
  "message": "二维码已过期"
}
```

---

## 获取用户会话

### GET /auth/session/{session_id}

获取当前登录状态

**响应**
```json
{
  "session_id": "xxxxx",
  "cookie": "xxxxx",
  "created_at": "2026-03-15T10:00:00"
}
```

---

## 删除用户会话

### DELETE /auth/session/{session_id}

登出，删除会话

**响应**
```json
{
  "success": true
}
```
