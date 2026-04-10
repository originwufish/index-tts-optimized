没问题！我已经**完全按你的要求修改**：
删除所有异步任务相关内容，**只保留 `return_audio=true` 同步返回音频**的 Postman 示例，同时保留**多人配音完整说明**。

这是最终、最干净、可直接上传 GitHub 的 **README.md**：

```markdown
# IndexTTS Optimized
IndexTTS2 语音合成优化增强版 | 生产级 TTS API 服务
**支持多说话人配音 / 角色切换 / 文本预处理 / 音频归一化**

## 项目介绍
本项目基于 IndexTTS2 构建高性能语音合成服务，在原版基础上优化文本处理、音频质量、服务稳定性，并提供标准化、可直接部署的 FastAPI 接口。
支持多人配音、角色切换、停顿控制、语速/音量/情感调节，适用于智能播报、多角色对话、有声内容生成等场景。

---

## 优化内容
### 1. 文本预处理优化
- 支持数字转中文（电话/数值/序号三种模式）
- 支持自定义拼音标注：汉字[pin1]
- 支持局部替换语法 `[replace:old=new]`
- 自动清理无效连字符、符号
- 支持停顿标签 `[pause:1.0]`

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
- 同步返回合成音频

### 4. 核心新增：多人配音（角色切换）
- 支持一句话内多个角色无缝切换配音
- 角色音频统一存放：`spk/` 文件夹
- 角色配置文件：`speakers.json`
- 角色切换标签：`[anchor:角色名:字数]`

---

## 新增功能
✅ 多人配音 / 多角色切换
✅ 自定义停顿时长
✅ 数字中文智能读法
✅ 音频响度归一化
✅ 语速/音量/情感调节
✅ 目标时长自动匹配
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

**系统依赖**
- ffmpeg
- ffprobe

---

## 快速启动
```bash
pip install -r requirements.txt
python app.py
```

服务端口：**8888 / 8890**
API 文档：`http://localhost:8888/docs`

---

# 🧑‍🧑‍🧒 多人配音（角色切换）使用说明
## 1. 文件夹结构
```
项目根目录/
├── spk/              <-- 存放所有角色参考音频
│   ├── speaker1.wav
│   ├── speaker2.wav
│   ├── teacher.wav
│   └── robot.wav
├── speakers.json      <-- 角色配置文件
└── app.py
```

## 2. 角色音频存放
将每个角色的参考音色音频（wav 格式）放入 **`spk/` 文件夹**

## 3. speakers.json 配置（直接复制可用）
```json
{
    "speaker1": "spk/speaker1.wav",
    "speaker2": "spk/speaker2.wav",
    "teacher": "spk/teacher.wav",
    "robot": "spk/robot.wav",
    "xiaomei": "spk/xiaomei.wav",
    "xiaonan": "spk/xiaonan.wav"
}
```

## 4. 多人配音标志位语法
```
[anchor:角色名:字数]
```
- **角色名**：必须与 `speakers.json` 中的 key 一致
- **字数**：从当前位置开始，后续多少个字使用该角色配音

### 使用示例
```
大家好[anchor:speaker2:6]我是二号角色[anchor:teacher:8]欢迎来到配音课堂
```

---

# 📌 Postman 接口使用示例（同步返回音频）

## 1. 创建语音合成任务
### 请求信息
- **URL**
  ```
  http://localhost:8888/api/v1/tts/tasks
  ```
- **Method**：`POST`
- **Content-Type**：`multipart/form-data`

### 请求参数
| 参数名 | 类型 | 必填 | 示例值 |
| --- | --- | --- | --- |
| text | string | 是 | 大家好[pause:0.5][anchor:speaker2:6]我是二号角色 |
| return_audio | bool | 是 | true |
| speed | float | 否 | 1.0 |
| volume | float | 否 | 1.0 |
| emo_weight | float | 否 | 0.65 |
| prompt_audio | file | 是 | 上传wav格式参考音频 |
| target_duration_sec | float | 否 | 10 |

### 可直接复制的测试文本
```
大家好[pause:0.5][anchor:speaker2:6]我是二号角色[pause:0.5][anchor:teacher:8]欢迎来到多配音课堂
```

### 成功返回
```json
{
    "output_audio_path": "/outputs/tasks/a7e40e5c-fd8d-40f6-b2d3-4224106e3093.wav",
    "status": 200
}
```

---

## 2. 健康检查
```
GET http://localhost:8888/health
```

### 返回
```json
{
    "status": "ok"
}
```

---

# 支持的标签语法
- 停顿：`[pause:0.5]`
- 角色切换：`[anchor:speaker1:6]`
- 拼音：`好[hao3]`
- 电话数字：`13800138000[phone:11]`
- 文本替换：`[replace:old=new]`

---

## 项目结构
```
index-tts-optimized/
├── app.py
├── requirements.txt
├── README.md
├── speakers.json
├── spk/
├── checkpoints/
├── outputs/
└── prompts/
```
```
