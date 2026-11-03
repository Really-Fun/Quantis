// Кнопка-«таблетка» в стиле Quantis: filled (акцент), light (белая),
// outlined (контур), text (только текст). Нажатие — затемнение и лёгкое
// сжатие без сдвига соседей; неактивная — приглушена.
import QtQuick
import QtQuick.Controls

AbstractButton {
    id: control
    property string variant: "filled"
    property bool compact: false
    property color textColor: variant === "light" ? theme.bg
                             : variant === "filled" ? theme.accentText
                             : theme.text

    implicitHeight: compact ? 40 : theme.touch
    implicitWidth: Math.max(implicitHeight, label.implicitWidth + (compact ? 32 : 44))
    opacity: enabled ? 1 : 0.4
    Accessible.role: Accessible.Button
    Accessible.name: text

    background: Rectangle {
        radius: height / 2
        color: control.variant === "filled" ? theme.accent
             : control.variant === "light" ? "#FFFFFF"
             : "transparent"
        border.width: control.variant === "outlined" ? 1 : 0
        border.color: theme.stroke
        scale: control.down ? 0.97 : 1
        Behavior on scale { NumberAnimation { duration: theme.fast } }
        Rectangle {
            anchors.fill: parent
            radius: parent.radius
            color: control.variant === "light" ? "#000000" : "#FFFFFF"
            opacity: control.down ? 0.14 : 0
            Behavior on opacity { NumberAnimation { duration: theme.fast } }
        }
    }

    contentItem: Text {
        id: label
        text: control.text
        color: control.textColor
        font.family: theme.ui
        font.pixelSize: control.compact ? 14 : 15
        font.weight: Font.Bold
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }
}
