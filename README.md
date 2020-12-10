# Local dev environment

### Layout

```sh
$ git clone https://github.com/carrier-io/pylon.git -b main pylon
$ git clone https://github.com/carrier-io/pylon.git -b local pylon-local
$ git clone https://github.com/carrier-io/pylon.git -b demo pylon-demo
$ cd pylon-local
```

### Specify local keys for Redis and MinIO

```sh
$ touch .env
$ echo 'REDIS_PASSWORD=redispassword' >> .env
$ echo 'MINIO_ACCESS_KEY=minioaccesskey' >> .env
$ echo 'MINIO_SECRET_KEY=miniosecretkey' >> .env
```

### Initialize

```sh
$ docker-compose up -d traefik minio
```

- Open your browser and go to http://localhost/minio/
- Login with your MINIO\_ACCESS\_KEY and MINIO\_SECRET\_KEY
- Create buckets: "module", "config"
- Upload file "base.zip" from "pylon-demo" folder to "module" bucket

```sh
$ docker-compose up -d && docker-compose logs -f
```

### Done
Head over to http://localhost/ to see your "Hello, World!" :)
