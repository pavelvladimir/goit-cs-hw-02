#!/usr/bin/env bash
set -euo pipefail

websites=(
    "https://google.com"
    "https://facebook.com"
    "https://twitter.com"
)

# Optional arguments replace the default list, e.g. ./check_websites.sh URL.
if (( $# > 0 )); then
    websites=("$@")
fi

if ! command -v curl >/dev/null 2>&1; then
    printf 'Error: curl is required.\n' >&2
    exit 1
fi

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# Containers can persist the log in a dedicated mounted directory.
log_file="${WEBSITE_LOG_FILE:-${script_dir}/website_status.log}"

log_error() {
    printf 'Error: cannot write log file: %s\n' "$log_file" >&2
    exit 1
}

# Each run records the current state of all requested websites.
if ! { : > "$log_file"; } 2>/dev/null; then
    log_error
fi

for website in "${websites[@]}"; do
    if http_code=$(curl --location --max-redirs 10 \
        --silent --show-error --output /dev/null \
        --connect-timeout 5 --max-time 15 \
        --write-out '%{http_code}' "$website") \
        && [[ "$http_code" == "200" ]]; then
        status="UP"
    else
        status="DOWN"
    fi

    if ! { printf '<%s> is %s\n' "$website" "$status" >> "$log_file"; } 2>/dev/null; then
        log_error
    fi
done

printf 'Results have been written to %s\n' "$log_file"
