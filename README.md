# Local dev environment

### Layout

```sh
git clone https://github.com/carrier-io/pylon.git -b main pylon
git clone https://github.com/carrier-io/pylon.git -b local pylon-local
git clone https://github.com/carrier-io/pylon.git -b demo pylon-demo
cd pylon-local
```

### Specify local keys for Redis and MinIO

```sh
touch .env
echo 'REDIS_PASSWORD=redispassword' >> .env
echo 'MINIO_ACCESS_KEY=minioaccesskey' >> .env
echo 'MINIO_SECRET_KEY=miniosecretkey' >> .env
echo 'RABBITMQ_USER=user' >> .env
echo 'RABBITMQ_PASSWORD=password' >> .env
```

### Initialize

```sh
python3 -m venv ../pylon-venv
../pylon-venv/bin/pip install -r requirements.txt

docker-compose up -d redis
../pylon-venv/bin/python provision.py --redis

docker-compose up -d traefik minio rabbitmq
../pylon-venv/bin/python provision.py --minio

docker-compose build && docker-compose up -d && docker-compose logs -f
```

### Done
Head over to http://localhost/ to see your "Hello, World!" :)
