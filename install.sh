#!/bin/bash

# Checking Root Access
if [[ $EUID -ne 0 ]]; then
    echo -e "\033[31m[ERROR]\033[0m Please run this script as \033[1mroot\033[0m."
    exit 1
fi

INSTALL_LOG="/tmp/candybot_install.log"
BOT_DIR="/opt/CandyBot"
REPO_URL="https://github.com/ednoct/CandyBot.git"

export DEBIAN_FRONTEND=noninteractive

# ── Menu UI helpers ──────────────────────────────────────────
C_BORDER=$'\033[1;36m'; C_TITLE=$'\033[1;37m'; C_DIM=$'\033[0;37m'
C_KEY=$'\033[1;33m';    C_TXT=$'\033[0;37m';   C_OK=$'\033[1;32m'
C_BAD=$'\033[1;31m';    C_WARN=$'\033[1;33m';  C_PROMPT=$'\033[1;36m'
CR=$'\033[0m'
UI_W=52

_repeat() { local ch="$1" n="$2" out="" i; for ((i=0;i<n;i++)); do out+="$ch"; done; printf '%s' "$out"; }
_rule()   { printf "  ${C_BORDER}%s${CR}\n" "$(_repeat "─" "$UI_W")"; }
_drule()  { printf "  ${C_BORDER}%s${CR}\n" "$(_repeat "━" "$UI_W")"; }
banner()  {
    echo
    _drule
    printf "  ${C_OK}▌${CR} ${C_TITLE}CANDY BOT${CR}  ${C_DIM}— Python Asynchronous Architecture${CR}\n"
    _drule
}
_mi()     { printf "    ${C_KEY}[%s]${CR}  ${C_TXT}%b${CR}\n" "$1" "$2"; }
_sec()    { printf "\n  ${C_KEY}▌${CR} ${C_TITLE}%s${CR}\n" "$1"; _rule; }
_kv()     { printf "    ${C_DIM}%-14s${CR}${C_BORDER}:${CR} %b${CR}\n" "$1" "$2"; }
_dot()    { case "$1" in ok) printf "${C_OK}●${CR}";; bad) printf "${C_BAD}●${CR}";; warn) printf "${C_WARN}●${CR}";; *) printf "${C_DIM}●${CR}";; esac; }

# ── Progress Engine ──────────────────────────────────────────
run_step() {
    local msg="$1" cmd="$2"
    printf " \033[1;33m⠋\033[0m \033[0;37m%s...\033[0m" "$msg"
    : > "$INSTALL_LOG"
    bash -c "$cmd" >> "$INSTALL_LOG" 2>&1
    local rc=$?
    if [ "$rc" -eq 0 ]; then
        printf "\r\033[K \033[1;32m✔\033[0m \033[0;37m%s\033[0m\n" "$msg"
    else
        printf "\r\033[K \033[1;31m✘\033[0m \033[0;37m%s\033[0m\n" "$msg"
        echo -e "\033[1;31m──────────────── Error details ─────────────────\033[0m"
        tail -n 15 "$INSTALL_LOG"
        echo -e "\033[1;31m─────────────────────────────────────────────────\033[0m"
        exit 1
    fi
    return "$rc"
}

# ── Validations ──────────────────────────────────────────────
validate_domain() { [[ "$1" =~ ^([a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}$ ]]; }
validate_token() { [[ "$1" =~ ^[0-9]{8,10}:[a-zA-Z0-9_-]{35}$ ]]; }

get_server_ip() {
    curl -fsSL --max-time 4 ifconfig.me 2>/dev/null || hostname -I | awk '{print $1}'
}

# ── Dashboard ────────────────────────────────────────────────
show_logo() {
    clear
    banner
    _sec "System Status"
    _kv "OS" "${C_DIM}$(lsb_release -d 2>/dev/null | cut -f2)${CR}"
    _kv "IP Address" "${C_DIM}$(get_server_ip)${CR}"
    
    local bot_s; bot_s=$(systemctl is-active candybot 2>/dev/null || echo "inactive")
    if [ "$bot_s" = "active" ]; then _kv "CandyBot" "$(_dot ok) ${C_OK}active${CR}"
    else _kv "CandyBot" "$(_dot bad) ${C_BAD}$bot_s${CR}"; fi
}

# ── Install Logic ────────────────────────────────────────────
install_bot() {
    clear
    banner
    _sec "Installation Preparation"
    
    if [ -d "$BOT_DIR" ]; then
        echo -e "  ${C_BAD}●${CR} ${C_BAD}CandyBot is already installed at $BOT_DIR.${CR}"
        sleep 2; return 1
    fi

    run_step "Updating system packages" "apt-get update -y"
    run_step "Installing dependencies (Python, Nginx, Certbot)" "apt-get install -y python3 python3-pip python3-venv python3-dev nginx certbot python3-certbot-nginx git curl jq ufw sqlite3"

    _sec "Bot Configuration"
    # 1. Get Domain
    read -p "  ❯ Enter your domain (e.g. api.domain.com): " YOUR_DOMAIN < /dev/tty
    while ! validate_domain "$YOUR_DOMAIN"; do
        echo -e "  ${C_BAD}Invalid domain format.${CR}"
        read -p "  ❯ Enter your domain: " YOUR_DOMAIN < /dev/tty
    done

    # 2. Get Token
    read -p "  ❯ Enter Telegram Bot Token: " YOUR_TOKEN < /dev/tty
    while ! validate_token "$YOUR_TOKEN"; do
        echo -e "  ${C_BAD}Invalid token format.${CR}"
        read -p "  ❯ Enter Telegram Bot Token: " YOUR_TOKEN < /dev/tty
    done

    # 3. Get Admin ID
    read -p "  ❯ Enter Admin Telegram ID: " YOUR_ADMIN < /dev/tty
    while [[ ! "$YOUR_ADMIN" =~ ^[0-9]+$ ]]; do
        echo -e "  ${C_BAD}Must be a number.${CR}"
        read -p "  ❯ Enter Admin Telegram ID: " YOUR_ADMIN < /dev/tty
    done

    _sec "Deployment"
    # Clone Repository
    run_step "Cloning repository" "git clone $REPO_URL $BOT_DIR"
    
    # Setup Virtual Environment
    run_step "Creating Python virtual environment" "python3 -m venv $BOT_DIR/venv"
    run_step "Installing Python requirements" "$BOT_DIR/venv/bin/pip install --upgrade pip && $BOT_DIR/venv/bin/pip install -r $BOT_DIR/requirements.txt"

    # Create .env file
    cat <<EOF > $BOT_DIR/.env
BOT_TOKEN="$YOUR_TOKEN"
ADMIN_IDS="$YOUR_ADMIN"
WEB_HOST="127.0.0.1"
WEB_PORT="8080"
CORS_ORIGIN="*"
WEBHOOK_DOMAIN="$YOUR_DOMAIN"
EOF
    run_step "Generating .env configuration" "chmod 600 $BOT_DIR/.env"

    # Initialize Database (SQLite)
    run_step "Initializing SQLite database" "cd $BOT_DIR && PYTHONPATH=$BOT_DIR $BOT_DIR/venv/bin/python -c 'import asyncio; from database.db_manager import init_db; asyncio.run(init_db())' 2>/dev/null || true"

    # Generate and Inject Web Admin Credentials
    WEB_ADMIN_USER="admin_$(cat /dev/urandom | tr -dc 'a-z0-9' | fold -w 4 | head -n 1)"
    WEB_ADMIN_PASS="$(cat /dev/urandom | tr -dc 'a-zA-Z0-9' | fold -w 10 | head -n 1)"
    
    run_step "Creating Web Admin User" "sqlite3 $BOT_DIR/candy.db \"INSERT INTO admins (username, password, role) VALUES ('$WEB_ADMIN_USER', '$WEB_ADMIN_PASS', 'admin');\""

    # Nginx Configuration
    local VHOST="/etc/nginx/sites-available/$YOUR_DOMAIN.conf"
    cat <<EOF > "$VHOST"
server {
    listen 80;
    server_name $YOUR_DOMAIN;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF
    run_step "Configuring Nginx Reverse Proxy" "ln -sf $VHOST /etc/nginx/sites-enabled/ && rm -f /etc/nginx/sites-enabled/default && systemctl restart nginx"

    # SSL Configuration
    run_step "Obtaining Let's Encrypt SSL" "certbot --nginx -d $YOUR_DOMAIN --non-interactive --agree-tos --register-unsafely-without-email"

    # Systemd Service
    cat <<EOF > /etc/systemd/system/candybot.service
[Unit]
Description=CandyBot Telegram & Web API Service
After=network.target

[Service]
User=root
WorkingDirectory=$BOT_DIR
Environment="PATH=$BOT_DIR/venv/bin"
ExecStart=$BOT_DIR/venv/bin/python run.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
    run_step "Creating Systemd service" "systemctl daemon-reload && systemctl enable candybot && systemctl start candybot"

    # Firewall
    run_step "Configuring Firewall (UFW)" "ufw allow 80/tcp && ufw allow 443/tcp >/dev/null 2>&1 || true"

    # Telegram Webhook
    run_step "Setting Telegram Webhook" "curl -s \"https://api.telegram.org/bot\$YOUR_TOKEN/setWebhook?url=https://\$YOUR_DOMAIN/webhook/main\" > /dev/null"

    clear
    banner
    _sec "Installation Complete"
    _kv "Bot Service" "${C_OK}Active (Systemd)${CR}"
    _kv "Web Panel URL" "${C_KEY}https://$YOUR_DOMAIN/admin/login${CR}"
    
    _sec "Web Panel Credentials"
    _kv "Username" "${C_KEY}$WEB_ADMIN_USER${CR}"
    _kv "Password" "${C_KEY}$WEB_ADMIN_PASS${CR}"
    printf "    ${C_WARN}!${CR} ${C_DIM}Please save these credentials somewhere safe.${CR}\n"

    echo ""
    read -p "  ❯ Press Enter to return to menu..." _ < /dev/tty
    show_menu
}

# ── Update Logic ─────────────────────────────────────────────
update_bot() {
    clear
    banner
    _sec "Update Process"
    
    if [ ! -d "$BOT_DIR" ]; then
        echo -e "  ${C_BAD}●${CR} ${C_BAD}CandyBot is not installed.${CR}"
        sleep 2; return 1
    fi

    run_step "Stopping CandyBot service" "systemctl stop candybot"
    run_step "Pulling latest code from GitHub" "cd $BOT_DIR && git fetch origin main && git reset --hard origin/main"
    run_step "Updating Python requirements" "$BOT_DIR/venv/bin/pip install -r $BOT_DIR/requirements.txt"
    
    # Run any new DB migrations if applicable
    run_step "Applying database migrations" "cd $BOT_DIR && PYTHONPATH=$BOT_DIR $BOT_DIR/venv/bin/python -c 'import asyncio; from database.db_manager import init_db; asyncio.run(init_db())' 2>/dev/null || true"
    
    run_step "Restarting CandyBot service" "systemctl restart candybot"

    echo -e "\n  ${C_OK}✔${CR} ${C_OK}Bot updated successfully.${CR}\n"
    read -p "  ❯ Press Enter to return to menu..." _ < /dev/tty
    show_menu
}

# ── Remove Logic ─────────────────────────────────────────────
remove_bot() {
    clear
    banner
    _sec "Removal Process"
    read -p "  ❯ Are you sure you want to completely remove CandyBot? [y/N]: " choice < /dev/tty
    if [[ ! "$choice" =~ ^[Yy]$ ]]; then
        return 0
    fi

    run_step "Stopping and disabling services" "systemctl stop candybot 2>/dev/null; systemctl disable candybot 2>/dev/null; rm -f /etc/systemd/system/candybot.service; systemctl daemon-reload"
    run_step "Removing Nginx configurations" "rm -f /etc/nginx/sites-enabled/*.conf /etc/nginx/sites-available/*.conf 2>/dev/null; systemctl restart nginx"
    run_step "Deleting bot directory" "rm -rf $BOT_DIR"
    
    echo -e "\n  ${C_OK}✔${CR} ${C_OK}CandyBot has been completely removed from this server.${CR}\n"
    exit 0
}

# ── Main Menu ────────────────────────────────────────────────
show_menu() {
    show_logo
    _sec "Menu"
    _mi "1" "Install CandyBot"
    _mi "2" "Update CandyBot (Pull latest from Git)"
    _mi "3" "Remove CandyBot"
    _mi "0" "Exit"
    _rule
    echo ""
    read -p "  ❯ Select an option [0-3]: " option < /dev/tty
    case $option in
        1) install_bot ;;
        2) update_bot ;;
        3) remove_bot ;;
        0) echo -e "\n${C_OK}Exiting...${CR}"; exit 0 ;;
        *) echo -e "\n${C_BAD}Invalid option.${CR}"; sleep 1; show_menu ;;
    esac
}

show_menu