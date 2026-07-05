#!/usr/bin/env bash
# setup-autossh-service.sh — Create a systemd autossh reverse tunnel service

main() {
    TGT_SERVICE_PATH=/etc/systemd/system/autossh-tunnel-"$PORT".service
    SERVICE_NAME=$(basename "$TGT_SERVICE_PATH")

    write-autossh-service
    restart-service
}

write-autossh-service() {
    sudo tee "$TGT_SERVICE_PATH" >/dev/null <<EOF
        [Unit]
        Description=AutoSSH tunnel service
        After=network-online.target
        Wants=network-online.target

        [Service]
        User=$USER
        Environment="AUTOSSH_GATETIME=0"
        ExecStart=/usr/bin/autossh -M 0 -N -o "PubkeyAuthentication=yes" -o "PasswordAuthentication=no" -i $SECRET_KEY_PATH -R ${PORT}:localhost:22 $BASTION_SERVER
        RestartSec=3
        Restart=always

        [Install]
        WantedBy=multi-user.target
EOF

    trim-whitespaces "$TGT_SERVICE_PATH"

    sudo chmod 644 "$TGT_SERVICE_PATH"

    echo -e "\nSee $TGT_SERVICE_PATH"
}

trim-whitespaces() {
    local fpath=$1
    sudo sed -i 's/^[[:space:]]*//' "$fpath"
}

restart-service() {
    sudo systemctl daemon-reload
    sudo systemctl stop "$SERVICE_NAME"
    sudo systemctl enable "$SERVICE_NAME"
    sudo systemctl restart "$SERVICE_NAME"
    sudo systemctl status "$SERVICE_NAME"
}

# Argument parsing
usage() {
    echo "Usage: $0 -p PORT -b BASTION_SERVER -s SECRET_KEY_PATH [-h]"
    echo "  -p PORT              Port number for the tunnel (e.g., 5098; numbers above 1,000 are recommended)"
    echo "  -b BASTION_SERVER        Target server (e.g., user@hostname)"
    echo "  -s SECRET_KEY_PATH   Path to the SSH private key (e.g., /home/<YOUR-USER-NAME>/.ssh/id_rsa)"
    echo "  -h                   Display this help message"
    exit 1
}

while getopts "p:b:s:h" opt; do
    case $opt in
    p) PORT=$OPTARG ;;
    b) BASTION_SERVER=$OPTARG ;;
    s) SECRET_KEY_PATH=$OPTARG ;;
    h) usage ;;
    *) usage ;;
    esac
done

if [ -z "$PORT" ] || [ -z "$BASTION_SERVER" ] || [ -z "$SECRET_KEY_PATH" ]; then
    usage
fi

# Main
main

# EOF
