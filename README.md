# IndexTTS Optimized
高性能 IndexTTS 语音合成服务优化版 | 多说话人 TTS / 文本预处理 / 音频归一化 / 异步任务 API

## 项目介绍
本项目基于 **IndexTTS2** 进行工程化优化，提供稳定、高性能、可直接生产部署的语音合成 API 服务。
支持多说话人切换、智能文本预处理、音频自动归一化、语速/音量/情感控制。

## 核心特性
✅ 多说话人无缝合成
✅ 文本预处理（数字转中文、自定义拼音、符号优化）
✅ 音频自动响度归一化
✅ 停顿控制 / 语速调节 / 音量调节
✅ 异步任务 + 同步返回双模式
✅ 双端口并发服务
✅ 完整 RESTful API
✅ 支持 MinIO 存储
✅ 生产级稳定部署

## 快速启动
```bash
# 安装依赖
pip install -r requirements.txt

# 放入模型文件到 checkpoints/
# 启动服务
python app.py
