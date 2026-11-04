// Страница приветствия: иллюстрация сверху, подпись, заголовок, текст и
// элементы выбора. Когда страница становится текущей, иллюстрация
// проявляется с лёгким увеличением, а текст выезжает снизу.
import QtQuick
import QtQuick.Layouts

Item {
    id: page
    property bool shown: false
    property string kicker
    property string title
    property string text
    property alias art: artBox.data // иллюстрация
    default property alias body: bodyBox.data // выбор под текстом
    property real artShare: 0.42 // доля высоты под иллюстрацию

    ColumnLayout {
        anchors.fill: parent
        anchors.leftMargin: 24
        anchors.rightMargin: 24
        anchors.topMargin: 16
        spacing: 0

        Item {
            Layout.fillWidth: true
            Layout.preferredHeight: page.height * page.artShare
            Item {
                id: artBox
                anchors.fill: parent
                opacity: page.shown ? 1 : 0
                scale: page.shown ? 1 : 0.86
                Behavior on opacity { NumberAnimation { duration: 520 } }
                Behavior on scale { NumberAnimation { duration: 700; easing.type: Easing.OutBack } }
            }
        }

        ColumnLayout {
            Layout.fillWidth: true
            spacing: 10
            opacity: page.shown ? 1 : 0
            Behavior on opacity { NumberAnimation { duration: 620; easing.type: Easing.OutCubic } }
            transform: Translate {
                y: page.shown ? 0 : 36
                Behavior on y { NumberAnimation { duration: 680; easing.type: Easing.OutCubic } }
            }

            Text {
                visible: page.kicker.length > 0
                text: page.kicker
                color: theme.accentCyan
                font.family: theme.ui
                font.pixelSize: 12
                font.weight: Font.Bold
                font.letterSpacing: 1.8
            }
            Text {
                Layout.fillWidth: true
                text: page.title
                color: theme.text
                wrapMode: Text.WordWrap
                font.family: theme.display
                font.pixelSize: 28
                font.weight: Font.DemiBold
                lineHeight: 1.1
            }
            Text {
                Layout.fillWidth: true
                visible: page.text.length > 0
                text: page.text
                color: theme.textDim
                wrapMode: Text.WordWrap
                font.family: theme.ui
                font.pixelSize: 15
                lineHeight: 1.25
            }
            ColumnLayout {
                id: bodyBox
                Layout.fillWidth: true
                Layout.topMargin: 14
                spacing: 10
            }
        }
        Item { Layout.fillHeight: true }
    }
}
