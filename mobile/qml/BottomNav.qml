// Нижняя панель из трёх вкладок: значок и подпись, активная — акцентом.
import QtQuick
import QtQuick.Controls
import QtQuick.Controls.Material
import QtQuick.Layouts

Rectangle {
    id: nav
    property int current: 0
    signal selected(int index)

    height: theme.navHeight
    color: theme.bg

    Rectangle { anchors.top: parent.top; width: parent.width; height: 1; color: theme.stroke }

    RowLayout {
        anchors.fill: parent
        spacing: 0
        Repeater {
            model: [
                { icon: "home", label: "Главная" },
                { icon: "search", label: "Поиск" },
                { icon: "library", label: "Медиатека" }
            ]
            delegate: ItemDelegate {
                id: tab
                required property int index
                required property var modelData
                readonly property bool active: nav.current === index
                Layout.fillWidth: true
                Layout.fillHeight: true
                Accessible.name: modelData.label
                Accessible.role: Accessible.PageTab
                onClicked: nav.selected(index)
                background: Item {}
                contentItem: ColumnLayout {
                    spacing: 4
                    Rectangle {
                        Layout.alignment: Qt.AlignHCenter
                        Layout.preferredWidth: 56
                        Layout.preferredHeight: 30
                        radius: 15
                        color: tab.active ? Qt.rgba(theme.accent.r, theme.accent.g, theme.accent.b, 0.22) : "transparent"
                        Behavior on color { ColorAnimation { duration: theme.medium } }
                        Image {
                            anchors.centerIn: parent
                            source: "icons/" + tab.modelData.icon + ".svg"
                            sourceSize: Qt.size(22, 22)
                            opacity: tab.active ? 1 : 0.6
                            Accessible.ignored: true
                        }
                    }
                    Text {
                        Layout.alignment: Qt.AlignHCenter
                        text: tab.modelData.label
                        color: tab.active ? theme.text : theme.textDim
                        font.family: theme.ui
                        font.pixelSize: 12
                        font.weight: tab.active ? Font.Bold : Font.Medium
                    }
                }
            }
        }
    }
}
