// Карточка выбора на приветствии: цветной значок, название, пояснение и
// кружок-отметка. Выбранная — с цветной рамкой и подсветкой.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

AbstractButton {
    id: card
    property string title
    property string subtitle
    property string iconName: ""
    property string letter: ""
    property color tone: theme.accentCyan
    property bool selected: false

    Layout.fillWidth: true
    implicitHeight: 72
    opacity: enabled ? 1 : 0.45
    Accessible.role: Accessible.RadioButton
    Accessible.checked: selected
    Accessible.name: title + (subtitle ? ", " + subtitle : "")

    background: Rectangle {
        radius: 18
        color: card.selected ? Qt.rgba(card.tone.r, card.tone.g, card.tone.b, 0.14)
                             : Qt.rgba(1, 1, 1, card.down ? 0.08 : 0.04)
        border.width: card.selected ? 2 : 1
        border.color: card.selected ? card.tone : Qt.rgba(1, 1, 1, 0.08)
        Behavior on color { ColorAnimation { duration: theme.medium } }
        Behavior on border.color { ColorAnimation { duration: theme.medium } }
        scale: card.down ? 0.98 : 1
        Behavior on scale { NumberAnimation { duration: theme.fast } }
    }

    contentItem: RowLayout {
        spacing: 14
        Rectangle {
            Layout.leftMargin: 14
            Layout.preferredWidth: 44
            Layout.preferredHeight: 44
            radius: 14
            color: Qt.rgba(card.tone.r, card.tone.g, card.tone.b, 0.2)
            Text {
                anchors.centerIn: parent
                visible: card.letter.length > 0
                text: card.letter
                color: card.tone
                font.family: theme.display
                font.pixelSize: 20
                font.weight: Font.Bold
            }
            Image {
                anchors.centerIn: parent
                visible: card.iconName.length > 0
                source: card.iconName ? "icons/" + card.iconName + ".svg" : ""
                sourceSize: Qt.size(22, 22)
                Accessible.ignored: true
            }
        }
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 2
            Text {
                Layout.fillWidth: true
                text: card.title
                color: theme.text
                font.family: theme.ui
                font.pixelSize: 16
                font.weight: Font.DemiBold
                elide: Text.ElideRight
            }
            Text {
                Layout.fillWidth: true
                visible: card.subtitle.length > 0
                text: card.subtitle
                color: theme.textDim
                font.family: theme.ui
                font.pixelSize: 13
                elide: Text.ElideRight
            }
        }
        Rectangle { // отметка
            Layout.rightMargin: 16
            Layout.preferredWidth: 22
            Layout.preferredHeight: 22
            radius: 11
            color: "transparent"
            border.width: 2
            border.color: card.selected ? card.tone : Qt.rgba(1, 1, 1, 0.25)
            Rectangle {
                anchors.centerIn: parent
                width: card.selected ? 12 : 0
                height: width
                radius: width / 2
                color: card.tone
                Behavior on width { NumberAnimation { duration: theme.medium; easing.type: Easing.OutBack } }
            }
        }
    }
}
