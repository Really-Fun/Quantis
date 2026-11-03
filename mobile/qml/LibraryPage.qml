// Медиатека. Шаг 1: аккаунт Яндекса. Любимое и история — шаг 3.
import QtQuick
import QtQuick.Controls
import QtQuick.Controls.Material
import QtQuick.Layouts

StackView {
    id: stack
    initialItem: root

    function openAccount() {
        if (stack.depth === 1)
            stack.push(accountPage)
    }

    Component {
        id: accountPage
        AccountPage { onBack: stack.pop() }
    }

    Item {
        id: root
        ColumnLayout {
            anchors.fill: parent
            spacing: 12

            Text {
                Layout.leftMargin: theme.gutter
                Layout.topMargin: 20
                text: "Медиатека"
                color: theme.text
                font.family: theme.display
                font.pixelSize: 26
                font.weight: Font.DemiBold
            }

            ItemDelegate {
                Layout.fillWidth: true
                Layout.leftMargin: theme.gutter - 4
                Layout.rightMargin: theme.gutter - 4
                height: 72
                Accessible.name: "Аккаунт Яндекс Музыки"
                onClicked: stack.push(accountPage)
                background: Rectangle {
                    radius: theme.radius
                    color: parent.down ? theme.surfaceHigh : theme.surface
                    Behavior on color { ColorAnimation { duration: theme.fast } }
                }
                contentItem: RowLayout {
                    spacing: 14
                    Rectangle {
                        Layout.preferredWidth: 44; Layout.preferredHeight: 44
                        radius: 22
                        color: theme.surfaceHigh
                        Image {
                            anchors.centerIn: parent
                            source: "icons/user.svg"
                            sourceSize: Qt.size(22, 22)
                            Accessible.ignored: true
                        }
                    }
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 2
                        Text {
                            text: "Яндекс Музыка"
                            color: theme.text
                            font.family: theme.ui
                            font.pixelSize: 16
                            font.weight: Font.DemiBold
                        }
                        Text {
                            Layout.fillWidth: true
                            text: app.loggedIn ? (app.account || "Вход выполнен") : "Не выполнен вход"
                            color: app.loggedIn ? theme.textDim : theme.yandex
                            font.family: theme.ui
                            font.pixelSize: 13
                            elide: Text.ElideRight
                        }
                    }
                    Image {
                        source: "icons/chevron-right.svg"
                        sourceSize: Qt.size(20, 20)
                        opacity: 0.5
                        Accessible.ignored: true
                    }
                }
            }
            Item { Layout.fillHeight: true }
        }
    }
}
