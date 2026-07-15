<?php
ini_set('error_log', 'error_log');
require_once __DIR__ . '/../config.php';
require_once __DIR__ . '/../jdf.php';
require_once __DIR__ . '/../botapi.php';
require_once __DIR__ . '/../Marzban.php';
require_once __DIR__ . '/../function.php';
require_once __DIR__ . '/../keyboard.php';
require_once __DIR__ . '/../panels.php';
require __DIR__ . '/../vendor/autoload.php';
use Endroid\QrCode\Builder\Builder;
use Endroid\QrCode\Encoding\Encoding;
use Endroid\QrCode\ErrorCorrectionLevel;
use Endroid\QrCode\Label\Font\OpenSans;
use Endroid\QrCode\Label\LabelAlignment;
use Endroid\QrCode\RoundBlockSizeMode;
use Endroid\QrCode\Writer\PngWriter;

$ManagePanel = new ManagePanel();
$data = json_decode(file_get_contents("php://input"), true);
if (!is_array($data)) {
    $data = $_REQUEST;
}
$hashid = trim((string) ($data['hashid'] ?? $data['hash_id'] ?? $data['Hash_id'] ?? ''));
$authority = trim((string) ($data['authority'] ?? $data['Authority'] ?? ''));
$StatusPayment = isset($data['status']) ? (int) $data['status'] : null;
error_log('[Tetra98] callback received: ' . json_encode([
    'status' => $StatusPayment,
    'hashid' => $hashid,
    'authority' => $authority,
    'method' => $_SERVER['REQUEST_METHOD'] ?? '',
], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES));
$setting = select("setting", "*");
$PaySetting = trim((string) getPaySettingValue("apitetra", ""));
$Payment_reports = null;
if ($hashid !== '') {
    $Payment_reports = select("Payment_report", "*", "id_order", $hashid, "select");
}
if (!$Payment_reports && $authority !== '') {
    $Payment_reports = select("Payment_report", "*", "dec_not_confirmed", $authority, "select");
}
if (!$Payment_reports) {
    error_log('[Tetra98] payment report not found: ' . json_encode([
        'hashid' => $hashid,
        'authority' => $authority,
    ], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES));
}
$invoice_id = $Payment_reports['id_order'] ?? $hashid;
$price = $Payment_reports['price'] ?? 0;
// verify Transaction
$dec_payment_status = "";
$payment_status = $textbotlang['paymentGateway']['statusFailed'];
if ($PaySetting !== "" && $PaySetting !== "0" && $Payment_reports && $StatusPayment == 100 && $authority !== '') {
    $curl = curl_init();
    $data = [
        "ApiKey" => $PaySetting,
        "authority" => $authority,
        "Hash_id" => $invoice_id,
    ];
    curl_setopt_array($curl, array(
        CURLOPT_URL => "https://tetra98.com/api/verify",
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_ENCODING => '',
        CURLOPT_MAXREDIRS => 10,
        CURLOPT_TIMEOUT => 20,
        CURLOPT_FOLLOWLOCATION => true,
        CURLOPT_HTTP_VERSION => CURL_HTTP_VERSION_1_1,
        CURLOPT_POSTFIELDS => json_encode($data),
        CURLOPT_POST => true,
        CURLOPT_HTTPHEADER => array(
            'Content-Type: application/json',
            'Accept: application/json'
        ),
    ));
    $responseBody = curl_exec($curl);
    $curlError = curl_error($curl);
    $httpCode = curl_getinfo($curl, CURLINFO_HTTP_CODE);
    curl_close($curl);
    if ($responseBody === false) {
        error_log('[Tetra98] verify curl failed: ' . $curlError);
        $response = null;
    } else {
        error_log('[Tetra98] verify response: ' . json_encode([
            'http_code' => $httpCode,
            'body' => $responseBody,
        ], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES));
        $response = json_decode($responseBody, true);
    }
    $verifiedHash = is_array($response) ? ($response['hash_id'] ?? $response['hashid'] ?? null) : null;
    $verifiedAuthority = is_array($response) ? ($response['authority'] ?? null) : null;
    if (is_array($response) && !empty($response['status']) && (int) $response['status'] === 100 && $verifiedAuthority === $authority && (!$verifiedHash || $verifiedHash === $invoice_id)) {
        $payment_status = $textbotlang['paymentGateway']['statusSuccess'];
        $dec_payment_status = $textbotlang['paymentGateway']['descThanks'];
        $Payment_report = $Payment_reports;
        if ($Payment_report['payment_Status'] != "paid") {
            $textbotlang = languagechange();
            DirectPayment($invoice_id, "../images.jpg");
            $pricecashback = select("PaySetting", "ValuePay", "NamePay", "chashbacktetra", "select")['ValuePay'];
            $Balance_id = select("user", "*", "id", $Payment_report['id_user'], "select");
            if ($pricecashback != "0") {
                $result = ($Payment_report['price'] * $pricecashback) / 100;
                $Balance_confrim = intval($Balance_id['Balance']) + $result;
                update("user", "Balance", $Balance_confrim, "id", $Balance_id['id']);
                $pricecashback = number_format($pricecashback);
                $text_report = sprintf($textbotlang['paymentGateway']['giftReport'], $result);
                sendmessage($Balance_id['id'], $text_report, null, 'HTML');
            }
            update("Payment_report", "payment_Status", "paid", "id_order", $Payment_report['id_order']);
            $paymentreports = select("topicid", "idreport", "report", "paymentreport", "select")['idreport'];
            $price = number_format($price);
            $text_report = sprintf($textbotlang['paymentGateway']['reportIranpay'], $Payment_report['id_user'], $Balance_id['username'], $price);
            if (strlen($setting['Channel_Report']) > 0) {
                telegram('sendmessage', [
                    'chat_id' => $setting['Channel_Report'],
                    'message_thread_id' => $paymentreports,
                    'text' => $text_report,
                    'parse_mode' => "HTML"
                ]);
            }
        }
    } else {
        $payment_status = $textbotlang['paymentGateway']['statusFailed'];
        $dec_payment_status = "";
        error_log('[Tetra98] verify rejected: ' . json_encode([
            'invoice_id' => $invoice_id,
            'authority' => $authority,
            'response' => $response,
        ], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES));
        if ($Payment_reports && $Payment_reports['payment_Status'] !== 'paid') {
            update("Payment_report", "payment_Status", "failed", "id_order", $Payment_reports['id_order']);
        }
    }
} elseif ($Payment_reports && $Payment_reports['payment_Status'] !== 'paid') {
    error_log('[Tetra98] callback ignored before verify: ' . json_encode([
        'invoice_id' => $invoice_id,
        'status' => $StatusPayment,
        'has_api_key' => ($PaySetting !== "" && $PaySetting !== "0"),
        'has_authority' => ($authority !== ''),
    ], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES));
    if ($StatusPayment !== 100) {
        update("Payment_report", "payment_Status", "failed", "id_order", $Payment_reports['id_order']);
    }
}
?>
<html>

<head>
    <title><?php echo $textbotlang['paymentGateway']['invoiceTitle'] ?></title>
    <style>
        @font-face {
            font-family: 'vazir';
            src: url('/Vazir.eot');
            src: local('☺'), url('../fonts/Vazir.woff') format('woff'), url('../fonts/Vazir.ttf') format('truetype');
        }

        body {
            font-family: vazir;
            background-color: #f2f2f2;
            margin: 0;
            padding: 20px;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
        }

        .confirmation-box {
            background-color: #ffffff;
            border-radius: 8px;
            width: 25%;
            box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1);
            padding: 40px;
            text-align: center;
        }

        h1 {
            color: #333333;
            margin-bottom: 20px;
        }

        p {
            color: #666666;
            margin-bottom: 10px;
        }
    </style>
</head>

<body>
    <div class="confirmation-box">
        <h1><?php echo $payment_status ?></h1>
        <p><?php echo $textbotlang['paymentGateway']['invoiceTransactionNo'] ?><span><?php echo $invoice_id ?></span></p>
        <p><?php echo $textbotlang['paymentGateway']['invoiceAmount'] ?> <span><?php echo $price ?></span><?php echo $textbotlang['paymentGateway']['invoiceAmountUnit'] ?></p>
        <p><?php echo $textbotlang['paymentGateway']['invoiceDate'] ?> <span> <?php echo jdate('Y/m/d') ?> </span></p>
        <p><?php echo $dec_payment_status ?></p>
    </div>
</body>

</html>
