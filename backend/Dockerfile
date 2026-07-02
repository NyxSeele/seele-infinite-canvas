FROM python:3.12-slim

# 镜头级视频风格参考（style_reference_service）依赖 ffmpeg / imageio-ffmpeg。
# 当前镜像未安装 — Docker 部署下该功能返回 503。
# 如需启用：取消下行注释并在 pip 步骤增加 imageio-ffmpeg
# RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV APP_ENV=production
ENV PYTHONUNBUFFERED=1

RUN mkdir -p uploads/images

COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

EXPOSE 7788

ENTRYPOINT ["/docker-entrypoint.sh"]
