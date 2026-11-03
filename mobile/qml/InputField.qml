// Поле ввода в стиле Quantis на базовом стиле Qt (не SearchField: так зовётся элемент Qt 6.10). У Material подсказка при
// фокусе «всплывала» над полем и наезжала на текст.
import QtQuick
import QtQuick.Controls.Basic as Basic

Basic.TextField {
    id: field
    property string iconName: ""

    color: theme.text
    placeholderTextColor: theme.textDim
    selectionColor: theme.accent
    selectedTextColor: theme.accentText
    font.family: theme.ui
    font.pixelSize: 16
    leftPadding: iconName ? 44 : 16
    rightPadding: 16
    topPadding: 14
    bottomPadding: 14
    verticalAlignment: TextInput.AlignVCenter

    background: Rectangle {
        implicitHeight: theme.touch + 4
        radius: theme.radius
        color: theme.surface
        border.color: field.activeFocus ? theme.accent : theme.stroke
        border.width: field.activeFocus ? 2 : 1
        Behavior on border.color { ColorAnimation { duration: theme.fast } }

        Image {
            visible: field.iconName.length > 0
            anchors.left: parent.left
            anchors.leftMargin: 14
            anchors.verticalCenter: parent.verticalCenter
            width: 20; height: 20
            source: field.iconName ? "icons/" + field.iconName + ".svg" : ""
            sourceSize: Qt.size(20, 20)
            opacity: 0.6
            Accessible.ignored: true
        }
    }
}
