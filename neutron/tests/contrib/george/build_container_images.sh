#!/usr/bin/env bash

# The directory structure is as follows:
# neutron/tests/contrib/george/build_container_images.sh
NEUTRON_DIR=$(dirname $(dirname $(dirname $(dirname $(dirname $(realpath $0))))))
CONTRIB_DIR=${CONTAINER_IMAGES_DIR:-$(dirname $(realpath $0))}
DOCKERFILE_SUFFIX=.Dockerfile

BUILD_IMAGE_ERROR=1


function build_image {
    local container_name=$1
    local Dockerfile=$2

    if sudo podman images | grep -q $container_name; then
        return
    fi
    sudo buildah bud -t $container_name -f $Dockerfile .
    if [ $? -ne 0 ]; then
        echo "Building an image $container_name failed!" 1>&2
        exit $BUILD_IMAGE_ERROR
    fi
}


function main {
    pushd $NEUTRON_DIR
    for Dockerfile in $(ls $CONTRIB_DIR/containers/*/*$DOCKERFILE_SUFFIX); do
        echo "Building an image from file $Dockerfile"
        name=$(basename -s $DOCKERFILE_SUFFIX $Dockerfile)
        build_image $name $Dockerfile
    done
    popd
}


main
