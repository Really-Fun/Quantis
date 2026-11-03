// Вход в Яндекс Музыку по OAuth-токену, как в настольном Quantis.
// Поле принимает вставку; статус проверки — под полем.
import QtQuick
import QtQuick.Controls
import QtQuick.Controls.Material
import QtQuick.Layouts

Item {
    id: page
    signal back()

    ColumnLayout {
        anchors.fill: parent
        anchors.leftMargin: theme.gutter
        anchors.rightMargin: theme.gutter
        spacing: 12

        RowLayout {
            Layout.topMargin: 8
            Layout.leftMargin: -12
            IconButton { iconName: "chevron-left"; label: "Назад"; onClicked: page.back() }
            Text {
                text: "Яндекс Музыка"
                color: theme.text
                font.family: theme.display
                font.pixelSize: 20
                font.weight: Font.DemiBold
            }
        }

        Text {
            Layout.fillWidth: true
            text: "Вставь OAuth-токен — тот же, что в Quantis на компьютере. Он хранится только на этом телефоне."
            color: theme.textDim
            wrapMode: Text.WordWrap
            font.family: theme.ui
            font.pixelSize: 14
        }

        TextField {
            id: token
            Layout.fillWidth: true
            placeholderText: "Токен"
            echoMode: TextInput.Password
            inputMethodHints: Qt.ImhSensitiveData | Qt.ImhNoPredictiveText
            font.family: theme.ui
            color: theme.text
            placeholderTextColor: theme.textDim
            leftPadding: 16
            topPadding: 14
            bottomPadding: 14
            background: Rectangle {
                radius: theme.radius
                color: theme.surface
                border.color: token.activeFocus ? theme.accent : theme.stroke
                border.width: token.activeFocus ? 2 : 1
            }
            Accessible.name: "OAuth-токен Яндекс Музыки"
            onAccepted: app.saveToken(text)
        }

        Text {
            Layout.fillWidth: true
            visible: text.length > 0
            text: app.account
            color: app.account.indexOf("не подошёл") >= 0 ? theme.danger : theme.textDim
            wrapMode: Text.WordWrap
            font.family: theme.ui
            font.pixelSize: 14
        }

        PillButton {
            Layout.fillWidth: true
            text: "Сохранить"
            enabled: token.text.trim().length > 0
            onClicked: app.saveToken(token.text)
        }
        PillButton {
            Layout.fillWidth: true
            text: "Выйти из аккаунта"
            variant: "text"
            textColor: theme.danger
            visible: app.loggedIn
            onClicked: { token.clear(); app.logout() }
        }
        Item { Layout.fillHeight: true }
    }
}
