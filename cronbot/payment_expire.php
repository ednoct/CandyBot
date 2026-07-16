<?php

ini_set('error_log', 'error_log');
date_default_timezone_set('Asia/Tehran');
require_once __DIR__ . '/../config.php';
require_once __DIR__ . '/../botapi.php';
require_once __DIR__ . '/../panels.php';
require_once __DIR__ . '/../function.php';
require __DIR__ . '/../vendor/autoload.php';
$ManagePanel = new ManagePanel();
$setting = select("setting", "*");
$textbotlang = languagechange();

// ─── 1. USDT / GRAM: Expiry handler (120 min / 24 hr) ───────────────────────
// Targets only the two offline gateways that store expires_at.
$stmt_usdt = $pdo->prepare(
    "SELECT * FROM Payment_report
     WHERE payment_Status = 'Unpaid'
       AND (Payment_Method = 'usdt offline' OR Payment_Method = 'gram offline')
       AND expires_at IS NOT NULL
       AND expires_at < UNIX_TIMESTAMP()"
);
$stmt_usdt->execute();

while ($expired = $stmt_usdt->fetch(PDO::FETCH_ASSOC)) {
    // 1a. Remove the invoice message from the user's Telegram chat
    deletemessage($expired['id_user'], $expired['message_id']);
    // 1b. Notify the user that their invoice has expired
    sendmessage($expired['id_user'], $textbotlang['hardcoded']['invoice_expired_msg'], null, 'HTML');
    // 1c. Mark the record as expired so it leaves the active queue
    update("Payment_report", "payment_Status", "expire", "id_order", $expired['id_order']);
}

// ─── 2. All gateways: 24-hour fallback expiry handler ────────────────
$month_date_time_start = time() - 86400;
$month_date_time_start = date('Y/m/d H:i:s', $month_date_time_start);
$stmt = $pdo->prepare("SELECT * FROM Payment_report WHERE time < :mp1 AND payment_Status = 'Unpaid'");
$stmt->execute([':mp1' => $month_date_time_start]);

while ($result = $stmt->fetch(PDO::FETCH_ASSOC)) {
    $status_var = [
        'cart to cart' =>  $textbotlang['textbot']['cartToCart'],
        'aqayepardakht' => $textbotlang['textbot']['aqayePardakht'],
        'zarinpal' => $textbotlang['textbot']['zarinPal'],
        'plisio' => $textbotlang['textbot']['nowPayment'],
        'arze digital offline' => $textbotlang['textbot']['nowPaymentTron'],
        'usdt offline' => $textbotlang['textbot']['nowPaymentUSDT'],
        'gram offline' => $textbotlang['textbot']['nowPaymentGRAM'],
        'Currency Rial 1' => $textbotlang['textbot']['iranPay2'],
        'Currency Rial 2' => $textbotlang['textbot']['iranPay3'],
        'Currency Rial 3' => $textbotlang['textbot']['iranPay1'],
        'Currency Rial tow' => $textbotlang['hardcoded']['gatewayRialName1'],
        'Currency Rial gateway3' => $textbotlang['hardcoded']['gatewayRialName2'],
        'perfect' => $textbotlang['hardcoded']['gatewayPerfectMoney'],
        'paymentnotverify' => $textbotlang['textbot']['paymentNotVerify'],
        'Star Telegram' => $textbotlang['textbot']['starTelegram'],
        'nowpayment' => $textbotlang['textbot']['cryptoPayment']
    ][$result['Payment_Method']];
    $textexpire = sprintf($textbotlang['hardcoded']['invoiceExpiredNotice'], $status_var, $result['id_order'], $result['price']);
// sendmessage($result['id_user'], $textexpire, null, 'html');
deletemessage($result['id_user'], $result['message_id']);
update("Payment_report","payment_Status","expire","id_order",$result['id_order']);
}