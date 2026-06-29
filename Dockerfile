FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# BuildKit copies host proxy settings into the build; the corporate proxy
# hostname is usually unreachable inside the container.
ARG HTTP_PROXY=
ARG HTTPS_PROXY=
ARG http_proxy=
ARG https_proxy=
ARG ALL_PROXY=
ARG NO_PROXY=*
ENV HTTP_PROXY=$HTTP_PROXY \
    HTTPS_PROXY=$HTTPS_PROXY \
    http_proxy=$http_proxy \
    https_proxy=$https_proxy \
    ALL_PROXY=$ALL_PROXY \
    NO_PROXY=$NO_PROXY \
    no_proxy=$NO_PROXY

COPY requirements.txt .
RUN HTTP_PROXY= HTTPS_PROXY= http_proxy= https_proxy= ALL_PROXY= NO_PROXY='*' \
    pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/

EXPOSE 8000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000", "--app-dir", "src"]
