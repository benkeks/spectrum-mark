#!/usr/bin/env bash
set -euo pipefail

root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
cd "$root"
if (( $# != 0 )); then
    printf 'Usage: bash build-artifact.sh\n' >&2
    exit 2
fi
for repository in . equivio mcrl2; do
    if [[ ! -e "$repository/.git" ]]; then
        printf 'Missing Git checkout: %s. Initialize the submodules before packaging.\n' "$repository" >&2
        exit 1
    fi
done
docker info > /dev/null

mkdir -p artifact-builds
bundle=$(mktemp -d "$root/artifact-builds/equivio-artifact-$(date -u +%Y%m%dT%H%M%SZ)-XXXXXX")
sources="$bundle/spectrum-mark"
file_list=$(mktemp)
finish() {
    status=$?
    rm -f -- "$file_list"
    if (( status != 0 )); then
        printf 'Artifact build failed; incomplete output remains at %s\n' "$bundle" >&2
    fi
}
trap finish EXIT

printf 'Assembling artifact at %s\n' "$bundle"
mkdir -p "$sources"
for repository in . equivio mcrl2; do
    (
        cd "$root/$repository"
        git ls-files -z --cached --others --exclude-standard \
            --exclude='results/' --exclude='examples/aut/' \
            --exclude='*.tar' --exclude='*.tar.gz' --exclude='*.zip' |
            while IFS= read -r -d '' file; do
                if [[ -f "$file" || -L "$file" ]]; then
                    printf '%s/%s\0' "$repository" "$file"
                fi
            done
    ) >> "$file_list"
done
tar --create --null --no-recursion \
    --exclude='.git' --exclude='__pycache__' --exclude='*.pyc' \
    --exclude='node_modules' --exclude='target' --exclude='build' \
    --exclude='.metals' --exclude='.bloop' --exclude='.bsp' --exclude='.vscode' \
    --files-from="$file_list" |
    tar --extract --directory="$sources"

cp "$sources/artifact/LICENSE" "$bundle/LICENSE"
sed 's|(../README.md)|(spectrum-mark/README.md)|g' \
    "$sources/artifact/README.md" > "$bundle/README.md"
for repository in . equivio mcrl2; do
    printf '%s %s\n' "$repository" "$(git -C "$repository" rev-parse HEAD)"
done > "$bundle/SOURCE-REVISIONS"

docker build --build-arg "JOBS=${JOBS:-2}" \
    --file "$sources/artifact/Dockerfile" --tag equivio-artifact "$sources"
docker run --rm --network=none equivio-artifact bash artifact/smoke-test.sh
docker save --output "$bundle/equivio-artifact.tar" equivio-artifact

(
    cd "$bundle"
    find . -type f ! -name SHA256SUMS -print0 | sort -z |
        xargs -0 sha256sum > SHA256SUMS
)
printf '\nArtifact ready: %s\n' "$bundle"
