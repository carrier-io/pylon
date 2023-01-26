# pylon

Plugin based galloper core

### Example command to build arm image:
`docker buildx build --platform linux/arm64 -f "Dockerfile" -t "pylon:local" .`

### Build command for latest pylon (add --push to push)
`docker buildx build --platform linux/amd64,linux/arm64 -t getcarrier/pylon:latest .`
