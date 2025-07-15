## 简介
检测 vps 是否正常的项目，如果不正常则删除 CloudFlare DNS 记录，待 vps 恢复后自动添加 DNS 记录。

## 设置变量
```bash
cp .env-example .env
```

- 登陆 Cloudflare Dashboard，创建一个有读写权限的 DNS 密钥。使用以下命令生成 ZONE_ID

先测试密钥是否有效
```bash
curl "https://api.cloudflare.com/client/v4/user/tokens/verify" \
     -H "Authorization: Bearer YOUR_API_KEY"
```

生成 ZONE_ID
```bash
curl -X GET "https://api.cloudflare.com/client/v4/zones" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json"
```

## 添加定时任务
```bash
*/2 * * * * root cd /root && /usr/bin/python3 dns_monitor.py
```
