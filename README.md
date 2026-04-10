这是**100% 匹配你最新代码、无版本号、干净整洁、可直接提交 GitHub**的最终版 `README.md`，直接全选复制即可使用：

```markdown
# IndexTTS Optimized
IndexTTS2 语音合成优化增强版 | 生产级 TTS API 服务

## 项目介绍
本项目基于 IndexTTS2 构建高性能语音合成服务，在原版基础上优化文本处理、音频质量、服务稳定性，并提供标准化、可直接部署的 FastAPI 接口。
支持多说话人、文本预处理、音频归一化、异步任务、语速/音量/情感调节等功能。

---

## 优化内容
### 1. 文本预处理优化
- 支持数字转中文（电话/数值/序号三种模式）
- 支持自定义拼音标注：汉字[pin1]
- 支持局部替换语法 [replace:old=new]
- 自动清理无效连字符、符号
- 支持停顿标签 [pause:1.0]

### 2. 音频合成质量优化
- 分段音频自动响度归一化（LUFS）
- 全局音量统一，避免忽大忽小
- 长文本自动切分 + 无缝拼接
- 支持语速、音量、情感强度调节
- 支持目标时长自动调速

### 3. 服务稳定性优化
- 启动时自动校验模型文件完整性
- 完善异常捕获与错误提示
- 自动清理临时文件
- 双端口并发服务（8888 / 8890）
- 支持同步返回 / 异步任务两种模式

### 4. 功能增强
- 多说话人无缝切换 [anchor:name:length]
- 异步任务队列 + 任务状态查询
- 支持 MinIO 对象存储上传
- 完整 RESTful API
- 服务监控接口 /metrics

---

## 新增功能
✅ 多说话人锚点合成  
✅ 自定义停顿时长  
✅ 数字中文读法  
✅ 音频响度归一化  
✅ 语速/音量/情感调节  
✅ 目标时长自动匹配  
✅ 异步任务调度  
✅ 任务状态查询  
✅ 健康检查接口  
✅ 监控指标接口  

---

## 环境依赖
```
fastapi
uvicorn
pydantic
python-multipart
cn2an
```

**系统依赖：**
- ffmpeg
- ffprobe

---

## 快速启动
1. 安装依赖
```bash
pip install -r requirements.txt
```

2. 放入模型文件到 `checkpoints/`
```
bpe.model
gpt.pth
config.yaml
s2mel.pth
wav2vec2bert_stats.pt
```

3. 启动服务
```bash
python app.py
```

4. API 文档
```
http://localhost:8888/docs
```

服务端口：8888、8890

---

## Postman 请求示例
### 接口地址
```
POST http://localhost:8888/api/v1/tts/tasks
```

### 请求格式
form-data

### 请求参数
| 参数名 | 说明 |
| --- | --- |
| text | 合成文本 |
| speed | 语速 默认 1.0 |
| volume | 音量 默认 1.0 |
| emo_weight | 情感权重 默认 0.65 |
| return_audio | 是否直接返回音频 |
| prompt_audio | 参考音色音频（必传） |
| emo_ref_audio | 情感参考音频（可选） |

### 示例文本
```
大家好[pause:0.5]欢迎使用IndexTTS优化版[anchor:speaker1:5]
```

### 返回示例
```json
{
    "output_audio_path": "/k3s/tts/xxx.wav",
    "status": 200
}
```

---

## 其他接口
- 任务查询：`GET /api/v1/tts/tasks/{task_id}`
- 结果获取：`GET /api/v1/tts/tasks/{task_id}/result`
- 健康检查：`GET /health`

---

## 项目结构
```
index-tts-optimized/
├── app.py                # 主服务
├── requirements.txt
├── README.md
├── speakers.json         # 说话人配置
├── checkpoints/          # 模型目录
├── outputs/              # 输出目录
└── prompts/              # 提示音频目录
```

---

## 支持语法
- 停顿：`[pause:0.5]`
- 说话人：`[anchor:speaker:6]`
- 拼音：`好[hao3]`
- 数字：`123[phone:3]`
- 替换：`[replace:old=new]`
```
