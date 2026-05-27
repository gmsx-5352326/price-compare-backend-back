# 价格比较后端系统 - AI增强版

这是一个集成了AI分析功能的商品价格比较后端系统，支持多渠道京东商品数据爬取和AI驱动的价格对比分析。

## 新增AI功能

### 1. AI价格对比分析
- `/api/ai/price-comparison` (POST) - AI驱动的商品价格对比分析
- 输入商品列表，AI分析价格差异、推荐指数和购买建议

### 2. AI价格趋势分析
- `/api/ai/price-trend` (POST) - AI驱动的价格趋势分析
- 分析商品历史价格数据，预测未来趋势

### 3. 京东搜索+AI分析
- `/api/jd/search-with-ai-analysis?keyword=关键词` - 京东搜索并AI价格分析
- 结合爬取的商品数据和AI分析，提供综合报告

## API使用示例

### AI价格对比分析
```bash
curl -X POST http://localhost:5000/api/ai/price-comparison \
  -H "Content-Type: application/json" \
  -d '{
    "products": [
      {
        "title": "iPhone 15 Pro",
        "price": "7999",
        "shop": "Apple官方旗舰店",
        "url": "https://item.jd.com/..."
      },
      {
        "title": "Samsung Galaxy S24", 
        "price": "6999",
        "shop": "Samsung官方旗舰店",
        "url": "https://item.jd.com/..."
      }
    ],
    "keyword": "手机"
  }'
```

### 京东搜索+AI分析
```bash
curl "http://localhost:5000/api/jd/search-with-ai-analysis?keyword=手机&pages=3"
```

## 技术架构

- Flask Web框架
- DrissionPage浏览器自动化
- DeepSeek AI API
- Supabase数据库
- 京东联盟API

## 环境配置

在 `.env` 文件中配置：

```env
# Supabase配置
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_key

# DeepSeek API配置
DEEPSEEK_API_KEY=your_deepseek_api_key
```

## 安装依赖

```bash
pip install -r requirements.txt
```

## 启动服务

```bash
python app.py
```

服务将在 `http://localhost:5000` 上运行。

## 功能特点

1. **多渠道数据采集**：
   - DrissionPage浏览器自动化爬取
   - 京东联盟API直连
   - PC端浏览器复用模式

2. **AI增强分析**：
   - 价格对比分析
   - 趋势预测
   - 购买建议
   - 推荐指数

3. **智能缓存**：
   - 登录态保持
   - 浏览器复用
   - AI分析结果缓存

4. **反反爬虫措施**：
   - 代理池支持
   - TLS指纹伪装
   - 随机延时
   - Cookie预热