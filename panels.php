<?php
ini_set('error_log', 'error_log');
require_once __DIR__ . '/config.php';

class ManagePanel
{
    public $pdo, $domainhosts, $name_panel;

    function createUser($name_panel, $code_product, $usernameC, array $Data_Config)
    {
        $Output = [];
        global $pdo, $domainhosts, $textbotlang;
        if (strlen($usernameC) < 3) {
            return array(
                "status" => "Unsuccessful",
                "msg" => "Username must be at least 3 characters long."
            );
        }
        $Get_Data_Panel = select("locations", "*", "name", $name_panel, "select");
        if ($Get_Data_Panel == false) {
            $Output['status'] = 'Unsuccessful';
            $Output['msg'] = 'Location Not Found';
            return $Output;
        }

        $statement = $pdo->prepare("SELECT * FROM manualsell WHERE codepanel = :code_panel AND status = 'active' AND codeproduct = :code_product ORDER BY RAND() LIMIT 1");
        $statement->bindParam(":code_panel", $Get_Data_Panel['code']);
        $statement->bindParam(":code_product", $code_product);
        $statement->execute();
        $configman = $statement->fetch(PDO::FETCH_ASSOC);
        $Output['status'] = 'successful';
        $Output['username'] = $usernameC;
        $Output['subscription_url'] = $configman['contentrecord'] ?? '';
        $Output['configs'] = "";
        if($configman) {
            update("manualsell", "status", "selled", "id", $configman['id']);
            update("manualsell", "username", $usernameC, "id", $configman['id']);
        }
        return $Output;
    }

    function DataUser($name_panel, $username)
    {
        global $pdo;
        $Get_Data_Panel = select("locations", "*", "name", $name_panel, "select");
        if ($Get_Data_Panel) {
            $stmt = $pdo->prepare("SELECT * FROM manualsell WHERE username = :username");
            $stmt->bindParam(':username', $username);
            $stmt->execute();
            $configman = $stmt->fetch(PDO::FETCH_ASSOC);
            $service = select("invoice", "*", "username", $username, "select");
            $Output = array(
                'status' => $service['Status'] ?? '',
                'username' => $service['username'] ?? '',
                'data_limit' => null,
                'expire' => $service['time_sell'] ?? '',
                'online_at' => null,
                'used_traffic' => null,
                'links' => [],
                'subscription_url' => $configman['contentrecord'] ?? '',
                'sub_updated_at' => null,
                'sub_last_user_agent' => null,
                'uuid' => null
            );
            return $Output;
        }
        return false;
    }

    function Revoke_sub($name_panel, $username)
    {
        return array('status' => 'successful');
    }

    function RemoveUser($name_panel, $username)
    {
        global $pdo;
        $Get_Data_Panel = select("locations", "*", "name", $name_panel, "select");
        if ($Get_Data_Panel) {
            update("manualsell", "status", "delete", "username", $username);
            return array(
                'status' => 'successful',
                'username' => $username,
            );
        }
        return array('status' => 'successful');
    }

    function Modifyuser($username, $name_panel, $config = array())
    {
        return array('status' => 'successful');
    }

    function Change_status($username, $name_panel)
    {
        return array('status' => 'successful', 'msg' => '');
    }

    function ResetUserDataUsage($username, $name_panel)
    {
        return array('status' => 'successful', 'msg' => '');
    }

    function extra_volume($username_account, $code_panel, $limit_volume_new)
    {
        return array('status' => 'successful');
    }

    function extra_time($username_account, $code_panel, $limit_time_new)
    {
        return array('status' => 'successful');
    }
}
