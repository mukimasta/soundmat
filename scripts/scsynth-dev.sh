#!/bin/sh
# 开发机上手动启动合成器服务（树莓派上由 systemd 服务启动，见 docs/implementation/DEPLOYMENT.md）。
# 用法：scripts/scsynth-dev.sh [声道数，默认 2]
# macOS 使用 CoreAudio 的默认输出设备；采样率 48 kHz 与声音素材一致。
CH="${1:-2}"
if [ -x /Applications/SuperCollider.app/Contents/Resources/scsynth ]; then
  SCSYNTH=/Applications/SuperCollider.app/Contents/Resources/scsynth
else
  SCSYNTH=scsynth
fi
exec "$SCSYNTH" -u 57110 -i 0 -o "$CH" -S 48000
