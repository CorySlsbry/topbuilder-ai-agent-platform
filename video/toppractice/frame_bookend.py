"""Frame a HeyGen avatar bookend: crop the center portrait out of the 16:9 pillarboxed render and
composite it onto a brand title card (presenter right, text left). Reusable for every intro/outro.
Usage: python frame_bookend.py <avatar.mp4> <bg.png> <out.mp4>"""
import subprocess, sys, pathlib

def frame(avatar, bg, out):
    avatar, bg, out = map(lambda p: str(pathlib.Path(p).resolve()), (avatar, bg, out))
    subprocess.run([
        "ffmpeg", "-y", "-loop", "1", "-i", bg, "-i", avatar,
        "-filter_complex",
        "[1:v]crop=600:1080:660:0,scale=478:860[fg];[0:v][fg]overlay=1300:130:shortest=1[v]",
        "-map", "[v]", "-map", "1:a", "-c:v", "libx264", "-preset", "veryfast",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-shortest", out], check=True)
    print("FRAMED ->", out)

if __name__ == "__main__":
    frame(sys.argv[1], sys.argv[2], sys.argv[3])
