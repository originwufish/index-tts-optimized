# coding=utf-8
import os
import sys
import uuid
import shutil
import argparse
from typing import Optional, List
import threading
import subprocess
import json
import re
import cn2an
from fastapi import FastAPI, HTTPException, BackgroundTasks, UploadFile, File, Form
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import time

# -----------------------------------------------------
# 路径初始化
# -----------------------------------------------------
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)
sys.path.append(os.path.join(current_dir, "tts"))

# -----------------------------------------------------
# Argument Parser
# -----------------------------------------------------
parser = argparse.ArgumentParser(
    description="IndexTTS API (Multi-Port Edition)",
    formatter_class=argparse.ArgumentDefaultsHelpFormatter,
)
parser.add_argument("--model_dir", type=str, default="./checkpoints")
parser.add_argument("--fp16", action="store_true", default=False)
parser.add_argument("--deepspeed", action="store_true", default=False)
parser.add_argument("--cuda_kernel", action="store_true", default=False)
cmd_args = parser.parse_args()

# -----------------------------------------------------
# 模型文件检查
# -----------------------------------------------------
if not os.path.exists(cmd_args.model_dir):
    print(f"Model directory {cmd_args.model_dir} does not exist.")
    sys.exit(1)

required_files = [
    "bpe.model",
    "gpt.pth",
    "config.yaml",
    "s2mel.pth",
    "wav2vec2bert_stats.pt"
]
for f in required_files:
    fp = os.path.join(cmd_args.model_dir, f)
    if not os.path.exists(fp):
        print(f"Missing required file: {fp}")
        sys.exit(1)

# -----------------------------------------------------
# 导入模型
# -----------------------------------------------------
from indextts.infer_v2 import IndexTTS2

# -----------------------------------------------------
# FastAPI 创建
# -----------------------------------------------------
app = FastAPI(
    title="IndexTTS API",
    description="IndexTTS2 Text-to-Speech API",
    version="1.0.6"
)

# -----------------------------------------------------
# 输出目录
# -----------------------------------------------------
os.makedirs("outputs/tasks", exist_ok=True)
app.mount("/outputs/tasks", StaticFiles(directory="outputs/tasks"), name="tasks")
os.makedirs("prompts", exist_ok=True)

# 清空旧任务
for filename in os.listdir("outputs/tasks"):
    path = os.path.join("outputs/tasks", filename)
    try:
        if os.path.isfile(path) or os.path.islink(path):
            os.unlink(path)
        else:
            shutil.rmtree(path)
    except:
        pass

# -----------------------------------------------------
# 初始化模型
# -----------------------------------------------------
tts = IndexTTS2(
    model_dir=cmd_args.model_dir,
    cfg_path=os.path.join(cmd_args.model_dir, "config.yaml"),
    use_fp16=cmd_args.fp16,
    use_deepspeed=cmd_args.deepspeed,
    use_cuda_kernel=cmd_args.cuda_kernel,
)


def generate_silence(path: str, duration: float):
    cmd = [
        "ffmpeg",
        "-y",
        "-f", "lavfi",
        "-i", "anullsrc=r=22050:cl=mono",
        "-t", str(duration),
        path
    ]
    subprocess.run(cmd, check=True)

def merge_audio_files(file_list, output_path):
    """
    使用 ffmpeg concat filter 无缝拼接音频段
    每段音频参数必须一致（采样率、声道、编码）
    file_list: 每段音频路径列表
    output_path: 输出路径
    """
    if not file_list:
        raise ValueError("file_list 不能为空")

    # 构建 filter_complex 拼接字符串
    inputs = []
    filter_cmd = ""
    for i, fp in enumerate(file_list):
        inputs.extend(["-i", fp])
        filter_cmd += f"[{i}:a]"
    filter_cmd += f"concat=n={len(file_list)}:v=0:a=1[outa]"

    # 执行 ffmpeg
    cmd = ["ffmpeg", "-y", *inputs, "-filter_complex", filter_cmd, "-map", "[outa]", output_path]
    subprocess.run(cmd, check=True)
    # os.remove(list_file)


# -----------------------------
# 文本预处理 & 数字/拼音/连字符
# -----------------------------
import re
import cn2an
import json
import os

phone_dict = {'1': '幺', '2': '二', '3': '三', '4': '四','5': '五','6': '六','7': '七','8': '八','9': '九','0': '零'}
sequence_dict = {'1': '一', '2': '二', '3': '三', '4': '四','5': '五','6': '六','7': '七','8': '八','9': '九','0': '零'}

def apply_local_replace(text: str) -> str:
    pattern = re.compile(r'\[replace:(.*?)=(.*?)\]')
    while True:
        match = pattern.search(text)
        if not match:
            break
        old, new = match.group(1), match.group(2)
        replace_pos = match.start()
        last_pos = text.rfind(old, 0, replace_pos)
        text = text[:match.start()] + text[match.end():]
        if last_pos != -1:
            text = text[:last_pos] + new + text[last_pos + len(old):]
    print(f"[DEBUG] replace 后 text: {text}")
    return text

def replace_numbers_with_chinese(text: str):
    pattern = re.compile(r'(\d+)\[(phone|value|sequence):(\d+)\]')
    def repl(match):
        num = match.group(1)
        type_ = match.group(2)
        count = int(match.group(3))
        tail = num[-count:]  # 要替换的数字
        if type_ == "phone":
            converted = "".join(phone_dict[x] for x in tail)
        elif type_ == "sequence":
            converted = "".join(sequence_dict[x] for x in tail)
        elif type_ == "value":
            converted = cn2an.an2cn(int(tail))  # 转中文数字
        else:
            return match.group(0)
        return num[:-count] + converted
    new_text = pattern.sub(repl, text)
    print(f"[DEBUG] 数字/value/sequence 后 text: {new_text}")
    return new_text

def apply_custom_pinyin(text: str) -> str:
    # 只匹配：汉字[拼音] → 替换为 [拼音]
    # 安全正则，绝不吞后面任何汉字！
    pattern = re.compile(r'([\u4e00-\u9fff])\[([a-zA-Z0-9]+)\]')
    new_text = pattern.sub(r'[\2]', text)
    print(f"[DEBUG] 拼音后 text: {new_text}")
    return new_text

def fix_hyphen(text: str):
    new_text = re.sub(r'-(?!\d)|(?<!\d)-', '', text)
    print(f"[DEBUG] 连字符修正后 text: {new_text}")
    return new_text

def preprocess_text(text: str):
    text = apply_local_replace(text)
    text = replace_numbers_with_chinese(text)
    text = apply_custom_pinyin(text)
    text = fix_hyphen(text)
    return text

# -----------------------------
# 读取说话人映射
# -----------------------------
with open("speakers.json", "r", encoding="utf-8") as f:
    speaker_map = json.load(f)


def parse_text_segments(text: str):
    print(f"[DEBUG] 初始传入 text: {text}")

    # 1. 过滤换行
    raw_text = text.replace("\n", "").replace("\r", "").strip()
    print(f"[DEBUG] 过滤换行/空白后 text: {raw_text}")

    import re

    # =====================
    # 核心：只移除【标签本身】，保留数字和文字
    # 移除：pause / replace / 拼音 / [value:] [sequence:] [phone:]
    # 保留：所有文字、数字、标点
    # =====================
    def clean_for_length(s):
        pattern = re.compile(
            r'\[pause:\d+\.?\d*\]'                # 停顿
            r'|\[replace:[^\]]+\]'                # 替换
            r'|\[\w+\]'                          # 拼音 [hao3]
            r'|\[(value|sequence|phone):\d+\]'   # 数字读法标签
        )
        return pattern.sub('', s)

    # =====================
    # 第一步：按真实朗读长度切分 anchor
    # =====================
    segments = []
    last_pos = 0
    anchor_pattern = re.compile(r'\[anchor=(\w+):(\d+)\]')

    for match in anchor_pattern.finditer(raw_text):
        prefix = raw_text[last_pos:match.start()]
        speaker = match.group(1)
        take_n = int(match.group(2))
        last_pos = match.end()

        clean = clean_for_length(prefix)
        need_keep = len(clean) - take_n if len(clean) >= take_n else 0

        # 遍历原文本，找到正确截取位置（只计有效字符，跳过标签）
        count = 0
        split_pos = 0
        i = 0
        while i < len(prefix) and count < need_keep:
            c = prefix[i]
            if c == '[':
                # 标签，直接跳过
                j = prefix.find(']', i)
                if j == -1:
                    j = i
                i = j + 1
                continue
            count += 1
            i += 1
        split_pos = i

        default_text = prefix[:split_pos]
        anchor_text = prefix[split_pos:]

        if default_text.strip():
            segments.append({"type": "tts", "speaker": "default", "text": default_text.strip()})
        if anchor_text.strip():
            segments.append({"type": "tts", "speaker": speaker, "text": anchor_text.strip()})

    # 剩余文本
    last_part = raw_text[last_pos:].strip()
    if last_part:
        segments.append({"type": "tts", "speaker": "default", "text": last_part})

    # =====================
    # 第二步：拆分 pause
    # =====================
    final = []
    pause_pattern = re.compile(r'\[pause:([\d\.]+)\]')
    for seg in segments:
        txt = seg["text"]
        spk = seg["speaker"]
        pos = 0
        for m in pause_pattern.finditer(txt):
            pre = txt[pos:m.start()]
            if pre.strip():
                final.append({"type": "tts", "speaker": spk, "text": pre.strip()})
            final.append({"type": "pause", "duration": float(m.group(1))})
            pos = m.end()
        rest = txt[pos:].strip()
        if rest:
            final.append({"type": "tts", "speaker": spk, "text": rest})

    # =====================
    # 输出结果
    # =====================
    print("\n[TEXT SEGMENTS STRUCTURE]")
    for i, s in enumerate(final):
        if s["type"] == "pause":
            print(f"段 {i} | pause {s['duration']} 秒")
        else:
            print(f"段 {i} | 说话人: {s['speaker']} | 文本：{s['text']}")
    print()

    return final


# -----------------------------
# 多段 TTS 生成 + 每段归一化 + 拼接 + 全局归一化
# -----------------------------
def generate_multi_speaker_audio(text, base_prompt_path, output_path, req):
    clean_text = text.replace("\n", "").strip()
    segments = parse_text_segments(clean_text)
    temp_files = []

    for i, seg in enumerate(segments):
        temp_path = output_path + f".seg{i}.wav"
        if seg["type"] == "pause":
            generate_silence(temp_path, seg["duration"])
        elif seg["type"] == "tts":
            speaker = seg["speaker"]
            prompt_path = base_prompt_path if speaker == "default" or speaker not in speaker_map else speaker_map[speaker]

            # 分段预处理文本
            processed_text = preprocess_text(seg["text"])

            # TTS 推理
            tts.infer(
                spk_audio_prompt=prompt_path,
                text=processed_text,
                output_path=temp_path,
                emo_alpha=req.emo_weight,
            )

        # ✅ 每段归一化
        normalized_path = temp_path.replace(".wav", "_norm.wav")
        normalize_audio(temp_path, normalized_path)
        temp_files.append(normalized_path)
        try: os.remove(temp_path)
        except: pass

    # 拼接所有段
    merged_path = output_path + ".merged.wav"
    merge_audio_files(temp_files, merged_path)

    # 删除中间段
    for f in temp_files:
        try: os.remove(f)
        except: pass

    # ✅ 最终全局归一化 + 调整速度/音量
    adjust_audio_ffmpeg(merged_path, output_path, req.speed, req.volume)
    try: os.remove(merged_path)
    except: pass


# -----------------------------
# 其他 TTS 系统函数保持不变
# -----------------------------
class TTSRequest(BaseModel):
    text: str
    return_audio: bool = False
    emo_weight: float = 0.65
    emo_vec: Optional[List[float]] = None
    emo_text: Optional[str] = None
    emo_random: bool = False
    speed: float = 1.0
    volume: float = 1.0
    max_text_tokens_per_segment: int = 120
    do_sample: bool = True
    top_p: float = 0.8
    top_k: int = 30
    temperature: float = 0.8
    length_penalty: float = 0.0
    num_beams: int = 3
    repetition_penalty: float = 10.0
    max_mel_tokens: int = 1500
    target_duration_sec: Optional[float] = None

tasks = {}

def auto_get_emo_mode(emo_ref_path, emo_vec, emo_text):
    if emo_text:
        return 3
    if emo_vec:
        return 2
    if emo_ref_path:
        return 1
    return 0

def get_audio_duration_sec(path: str) -> float:
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        path
    ]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe error: {result.stderr}")
    try:
        duration = float(result.stdout.strip())
        return duration
    except ValueError:
        raise RuntimeError(f"Cannot parse duration: {result.stdout}")


# -----------------------------
# 音频归一化函数
# -----------------------------
def normalize_audio(input_path: str, output_path: str, target_loudness=-22.0):
    """
    使用 ffmpeg loudnorm 将音频归一化到目标响度
    target_loudness: LUFS, 默认 -22 LUFS
    """
    cmd = [
        "ffmpeg", "-y", "-i", input_path,
        "-af", f"loudnorm=I={target_loudness}:LRA=11:TP=-1.5",
        output_path
    ]
    subprocess.run(cmd, check=True)


def adjust_audio_ffmpeg(input_path: str, output_path: str, speed: float = 1.0, volume: float = 1.0):
    """
    调整速度 + 音量 + loudnorm
    """
    if speed <= 0: speed = 1.0
    if volume <= 0: volume = 1.0

    # 速度分段处理
    atempo_filters = []
    remaining_speed = speed
    while remaining_speed > 2.0:
        atempo_filters.append("atempo=2.0")
        remaining_speed /= 2.0
    while remaining_speed < 0.5:
        atempo_filters.append("atempo=0.5")
        remaining_speed /= 0.5
    atempo_filters.append(f"atempo={remaining_speed}")

    # 拼接滤镜：速度 + 音量 + loudnorm
    filter_str = ",".join(atempo_filters + [f"volume={volume}", "loudnorm=I=-22:LRA=11:TP=-1.5"])
    tmp_path = output_path + ".tmp.wav"
    cmd1 = ["ffmpeg", "-y", "-i", input_path, "-filter:a", filter_str, tmp_path]
    subprocess.run(cmd1, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)

    # 输出最终音频
    cmd2 = ["ffmpeg", "-y", "-i", tmp_path, output_path]
    subprocess.run(cmd2, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)

    try: os.remove(tmp_path)
    except: pass

# =========================
# ⭐ 新增：Monitoring & MinIO
# =========================
from monitoring import Monitoring
# from minio_uploader import upload_file_to_minio
mon = Monitoring("indextts", "001", use_gpu=False)
mon.attach(app, metrics_path="/metrics")
mon.startup()
# =========================

# -----------------------------------------------------
# 后台任务
# -----------------------------------------------------
def process_tts_task(task_id: str, text: str, prompt_path: str, emo_ref_path: str, req: TTSRequest):
    try:
        tasks[task_id]["status"] = "processing"
        raw_path = os.path.join("outputs/tasks", f"{task_id}_raw.wav")
        final_path = os.path.join("outputs/tasks", f"{task_id}.wav")
        emo_control_method = auto_get_emo_mode(emo_ref_path, req.emo_vec, req.emo_text)
        emo_vector = None
        if emo_control_method == 2:
            emo_vector = tts.normalize_emo_vec(req.emo_vec, apply_bias=True)
        # 生成多主播音频
        generate_multi_speaker_audio(text, prompt_path, raw_path, req)
        if getattr(req, "target_duration_sec", None) and req.target_duration_sec > 0:
            duration = get_audio_duration_sec(raw_path)
            auto_speed = duration / req.target_duration_sec
            req.speed = req.speed * auto_speed
        adjust_audio_ffmpeg(raw_path, final_path, req.speed, req.volume)
        processed_duration = get_audio_duration_sec(final_path)
        print(f"[TTS] 处理后时长: {processed_duration:.3f} 秒")
        try: os.remove(raw_path)
        except: pass

        if os.path.exists(final_path):
            filename = os.path.basename(final_path)
            object_key = f"indextts/{filename}"
            try:
                # 上传 MinIO
                upload_file_to_minio(final_path, object_key)
                # 上传成功删除本地
                try: os.remove(final_path)
                except: pass
                tasks[task_id]["result_path"] = f"/k3s/{object_key}"
            except Exception as e:
                # 上传失败，保留本地文件，返回本地路径
                print(f"[MinIO] 上传失败，使用本地文件: {str(e)}")
                tasks[task_id]["result_path"] = f"/outputs/tasks/{filename}"

        tasks[task_id]["status"] = "completed"
        mon.send_call_log("/api/v1/tts/tasks", duration_sec=0, filename=f"{task_id}.wav")
    except Exception as e:
        tasks[task_id]["status"] = "failed"
        tasks[task_id]["message"] = str(e)
        mon.send_call_log("/api/v1/tts/tasks", duration_sec=0, filename=f"{task_id}.wav")

# -------------------- 页面 --------------------
@app.get("/")
def hello():
    return "szf_tts"

@app.get("/health")
def health():
    return {"status": "ok"}

# -----------------------------------------------------
# 创建任务接口
# -----------------------------------------------------
@app.post("/api/v1/tts/tasks")
async def create_tts_task(
    background_tasks: BackgroundTasks,
    text: str = Form(...),
    return_audio: bool = Form(False),
    speed: float = Form(1.0),
    volume: float = Form(1.0),
    prompt_audio: UploadFile = File(...),
    emo_ref_audio: UploadFile = File(None),
    emo_vec: str = Form(None),
    emo_text: str = Form(None),
    emo_weight: float = Form(0.65),
    emo_random: bool = Form(False),
    target_duration_sec: float = Form(None),
):

    start_ts = time.time()
    parsed_vec = None
    if emo_vec:
        try: parsed_vec = json.loads(emo_vec)
        except: raise HTTPException(400, "emo_vec must be a JSON list")

    req = TTSRequest(
        text=text, return_audio=return_audio, emo_weight=emo_weight,
        emo_text=emo_text, emo_random=emo_random, emo_vec=parsed_vec,
        speed=speed, volume=volume,target_duration_sec=target_duration_sec
    )

    task_id = str(uuid.uuid4())
    prompt_path = f"prompts/{task_id}_prompt.wav"
    with open(prompt_path, "wb") as f: f.write(await prompt_audio.read())

    emo_ref_path = None
    if emo_ref_audio:
        emo_ref_path = f"prompts/{task_id}_emo.wav"
        with open(emo_ref_path, "wb") as f: f.write(await emo_ref_audio.read())

    if return_audio:
        raw_path = os.path.join("outputs/tasks", f"{task_id}_raw.wav")
        final_path = os.path.join("outputs/tasks", f"{task_id}.wav")
        generate_multi_speaker_audio(text, prompt_path, raw_path, req)
        if getattr(req, "target_duration_sec", None) and req.target_duration_sec > 0:
            duration = get_audio_duration_sec(raw_path)
            auto_speed = duration / req.target_duration_sec
            req.speed = req.speed * auto_speed
        adjust_audio_ffmpeg(raw_path, final_path, req.speed, req.volume)
        try: os.remove(raw_path)
        except: pass

        filename = os.path.basename(final_path)
        object_key = f"tts/{filename}"
        audio_path = ""

        try:
            upload_file_to_minio(final_path, object_key)
            try: os.remove(final_path)
            except: pass
            audio_path = f"/k3s/{object_key}"
        except Exception as e:
            print(f"[MinIO] 上传失败，使用本地文件: {str(e)}")
            audio_path = f"/outputs/tasks/{filename}"

        mon.send_call_log("/api/v1/tts/tasks", duration_sec=time.time()-start_ts, filename=filename)
        return JSONResponse({"output_audio_path": audio_path, "status": 200})

    tasks[task_id] = {"status": "pending", "message": "Task created", "result_path": None}
    background_tasks.add_task(process_tts_task, task_id, text, prompt_path, emo_ref_path, req)
    mon.send_call_log("/api/v1/tts/tasks", duration_sec=time.time()-start_ts, filename=f"{task_id}.wav")
    return {"task_id": task_id, "status": "pending", "message": "Task created"}

# -----------------------------------------------------
# 查询任务状态
# -----------------------------------------------------
@app.get("/api/v1/tts/tasks/{task_id}")
async def get_task_status(task_id: str):
    if task_id not in tasks:
        raise HTTPException(404, "Task not found")
    return tasks[task_id]

# -----------------------------------------------------
# 获取生成结果
# -----------------------------------------------------
@app.get("/api/v1/tts/tasks/{task_id}/result")
async def get_task_result(task_id: str):
    if task_id not in tasks:
        raise HTTPException(404, "Task not found")
    t = tasks[task_id]
    if t["status"] != "completed":
        raise HTTPException(400, f"Task not completed ({t['status']})")
    result_path = t["result_path"]
    if not result_path:
        raise HTTPException(404, "Result file missing")
    return {"audio_path": result_path}


# -----------------------------------------------------
# 双端口运行
# -----------------------------------------------------
if __name__ == "__main__":
    import uvicorn

    def run_port(port):
        uvicorn.run(app, host="0.0.0.0", port=port)

    t1 = threading.Thread(target=run_port, args=(8888,))
    t2 = threading.Thread(target=run_port, args=(8890,))
    t1.start()
    t2.start()
    t1.join()
    t2.join()