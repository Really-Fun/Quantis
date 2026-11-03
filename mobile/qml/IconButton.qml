// Кнопка-значок: область касания 48 dp, отклик Material, подпись для диктора.
import QtQuick
import QtQuick.Controls
import QtQuick.Controls.Material

ToolButton {
    id: control
    property string iconName
    property real iconSize: 24
    property color tint: theme.text
    property string label

    implicitWidth: theme.touch
    implicitHeight: theme.touch
    icon.source: iconName ? "icons/" + iconName + ".svg" : ""
    icon.width: iconSize
    icon.height: iconSize
    icon.color: enabled ? tint : Qt.rgba(tint.r, tint.g, tint.b, 0.35)
    display: AbstractButton.IconOnly
    Accessible.name: label
    ToolTip.text: label
    ToolTip.visible: hovered && label.length > 0
    ToolTip.delay: 600
}
