# YTPoop LLM Music Video Generator

ใส่เพลงเข้าไป ได้ MV ออกมา — beat-synced kinetic typography rendered on GPU

> ไอเดียเริ่มจาก: ถ้าเราแปลงเพลงให้เป็นข้อมูล JSON แล้วป้อนให้ AI จัดการ มันจะเล่นภาพตามจังหวะได้มั้ย?

![style: cyberpunk kinetic typography, glitch, VHS]

---

## ทำอะไรได้บ้าง

- วิเคราะห์เสียงเพลง → จับ beat, bass, RMS, spectrum per frame
- Render ตัวอักษรเคลื่อนไหว sync กับ beat แบบ real-time บน GPU (PyTorch + ffmpeg)
- Glitch, VHS, Chromatic Aberration, Bloom, Scanlines
- Web UI สำหรับปรับแต่ง: เลือก color palette, segment, effect, background image/video
- ใส่ lyrics → ให้ Ollama (AI local) generate คำ/ประโยคให้เข้ากับเพลง
- Preview 10 วินาทีก่อน render เต็ม
- Save/Load preset

---

## Requirements

- Python 3.10+
- NVIDIA GPU + CUDA (หรือใช้ CPU แต่ช้ากว่า)
- ffmpeg (ติดตั้งอัตโนมัติผ่าน `install.bat`)
- [Ollama](https://ollama.ai) + model `qwen2.5` (optional — สำหรับ generate lyrics)

---

## Quick Start (Windows)

```
1. ดับเบิลคลิก  install.bat     ← ติดตั้งทุกอย่าง (ครั้งแรกครั้งเดียว)
2. ดับเบิลคลิก  run_webui.bat   ← เปิดใช้งาน
3. ดับเบิลคลิก  update.bat      ← อัปเดตเมื่อมีเวอร์ชันใหม่
```

`install.bat` จะจัดการให้ทั้งหมด:
- สร้าง `.venv` (Python virtual environment) แยกไม่ชนกับระบบ
- ดาวน์โหลด ffmpeg portable มาไว้ในโฟลเดอร์โปรเจค (ไม่ต้อง set PATH เอง)
- `pip install` ทุก dependency ใน `.venv`

> **หมายเหตุ**: ถ้า torch ลงไม่สำเร็จ (ต้องการ CUDA version เฉพาะ) ให้รันเอง:
> ```
> .venv\Scripts\activate.bat
> pip install torch --index-url https://download.pytorch.org/whl/cu121
> ```

---

## วิธีใช้

### Web UI (แนะนำ)

ดับเบิลคลิก `run_webui.bat` แล้วเปิด http://localhost:7861

### Command Line

```bash
# Activate venv ก่อน
.venv\Scripts\activate.bat

# Step 1: วิเคราะห์เพลง
python step1_analyze.py "song.mp3" -o analysis.json

# Step 2: Render MV
python step2_render.py analysis.json -o output.mp4
```

---

## Fonts (Windows)

ระบบใช้ฟอนต์จาก `C:\Windows\Fonts` — รองรับอัตโนมัติ:

| ภาษา | ฟอนต์ |
|------|-------|
| ภาษาไทย | Leelawadee UI |
| ภาษาญี่ปุ่น | Yu Gothic |
| ภาษาจีน | Microsoft YaHei |
| ภาษาเกาหลี | Malgun Gothic |
| ภาษาฮินดี | Nirmala UI |
| Latin | Segoe UI |

---

## Segments

| Segment | ลักษณะ |
|---------|--------|
| Hook | Impact words ทุก beat + pouring text — ดึงความสนใจ |
| Kinetic | ประโยคบินเข้า/ออก sync 4/4 |
| Terminal Log | Terminal scrolling พร้อม timestamp |
| Chat | บทสนทนา user/assistant |
| Pouring Text | Matrix-style ตัวอักษรไหลลงมา |
| Attention Grid | Heatmap visualizer |
| System Prompt | Tech lines กระจาย |
| Existential | ความคิด cascading |
| Question | Cinematic text reveal |
| Finale | Big statements ตอนจบ |

---

## License

MIT
