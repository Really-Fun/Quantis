// Полноэкранный плеер: выезжает снизу, свайп вниз или «⌄» сворачивают.
// Фон — цвет обложки (размытая обложка — шаг 2).
import QtQuick
import QtQuick.Controls
import QtQuick.Controls.Material
import QtQuick.Layouts

Drawer {
    id: sheet
    edge: Qt.BottomEdge
    interactive: opened // открывается кнопкой/мини-плеером, закрывается и свайпом
    dragMargin: 0
    modal: true
    dim: false

    readonly property var colors: theme.coverColors(app.title)

    background: Rectangle {
        color: theme.bg
        Rectangle {
            anchors.fill: parent
            gradient: Gradient {
                GradientStop { position: 0; color: Qt.darker(sheet.colors[0], 1.15) }
                GradientStop { position: 0.55; color: Qt.darker(sheet.colors[1], 1.6) }
                GradientStop { position: 1; color: theme.bg }
            }
            Behavior on opacity { NumberAnimation { duration: theme.medium } }
        }
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.leftMargin: 24
        anchors.rightMargin: 24
        anchors.topMargin: sheet.topPadding
        spacing: 0

        RowLayout {
            Layout.fillWidth: true
            Layout.topMargin: 8
            Layout.leftMargin: -12
            Layout.rightMargin: -12
            IconButton { iconName: "chevron-down"; label: "Свернуть плеер"; onClicked: sheet.close() }
            Text {
                Layout.fillWidth: true
                horizontalAlignment: Text.AlignHCenter
                text: "СЕЙЧАС ИГРАЕТ"
                color: Qt.rgba(1, 1, 1, 0.75)
                font.family: theme.ui
                font.pixelSize: 12
                font.weight: Font.Bold
                font.letterSpacing: 1.6
            }
            Item { implicitWidth: theme.touch; implicitHeight: theme.touch }
        }

        Item { Layout.fillHeight: true; Layout.minimumHeight: 8 }

        CoverArt {
            id: cover
            Layout.alignment: Qt.AlignHCenter
            Layout.preferredWidth: Math.min(sheet.width - 48, sheet.height * 0.42)
            Layout.preferredHeight: Layout.preferredWidth
            radius: 24
            glyph: 0.3
            seed: app.title
        }

        Item { Layout.fillHeight: true; Layout.minimumHeight: 16 }

        RowLayout {
            Layout.fillWidth: true
            spacing: 12
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 6
                Text {
                    Layout.fillWidth: true
                    text: app.title
                    color: theme.text
                    font.family: theme.display
                    font.pixelSize: 22
                    font.weight: Font.DemiBold
                    elide: Text.ElideRight
                }
                RowLayout {
                    spacing: 8
                    SourceBadge { source: app.trackSource }
                    Text {
                        Layout.fillWidth: true
                        text: app.loading ? "Загружаем…" : app.artist
                        color: Qt.rgba(1, 1, 1, 0.72)
                        font.family: theme.ui
                        font.pixelSize: 15
                        elide: Text.ElideRight
                    }
                }
            }
        }

        Slider {
            id: seek
            Layout.fillWidth: true
            Layout.topMargin: 12
            Layout.leftMargin: -6
            Layout.rightMargin: -6
            from: 0
            to: Math.max(1, app.duration)
            value: pressed ? value : app.position
            enabled: app.duration > 0
            Material.accent: theme.text
            Accessible.name: "Позиция в треке"
            onMoved: {}
            onPressedChanged: if (!pressed) app.seek(value)
        }
        RowLayout {
            Layout.fillWidth: true
            Text {
                text: theme.formatTime(seek.pressed ? seek.value : app.position)
                color: theme.textDim
                font.family: theme.ui
                font.pixelSize: 12
                font.features: { "tnum": 1 }
            }
            Item { Layout.fillWidth: true }
            Text {
                text: theme.formatTime(app.duration)
                color: theme.textDim
                font.family: theme.ui
                font.pixelSize: 12
                font.features: { "tnum": 1 }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.topMargin: 12
            spacing: 0
            IconButton {
                iconName: "shuffle"
                label: app.shuffle ? "Перемешивание включено" : "Перемешивание выключено"
                tint: app.shuffle ? theme.accentCyan : theme.textDim
                checked: app.shuffle
                onClicked: app.toggleShuffle()
            }
            Item { Layout.fillWidth: true }
            IconButton { iconName: "skip-back"; label: "Предыдущий трек"; iconSize: 28; onClicked: app.previous() }
            Item { Layout.fillWidth: true }
            PlayButton { size: 76 }
            Item { Layout.fillWidth: true }
            IconButton { iconName: "skip-forward"; label: "Следующий трек"; iconSize: 28; onClicked: app.next() }
            Item { Layout.fillWidth: true }
            IconButton {
                iconName: app.repeatMode === 2 ? "repeat-one" : "repeat"
                label: ["Повтор выключен", "Повтор очереди", "Повтор трека"][app.repeatMode]
                tint: app.repeatMode === 0 ? theme.textDim : theme.accentCyan
                onClicked: app.cycleRepeat()
            }
        }

        Text {
            Layout.fillWidth: true
            Layout.topMargin: 8
            horizontalAlignment: Text.AlignHCenter
            visible: text.length > 0
            text: app.status
            color: theme.danger
            wrapMode: Text.WordWrap
            font.family: theme.ui
            font.pixelSize: 13
        }

        Item { Layout.fillHeight: true; Layout.minimumHeight: 16; Layout.maximumHeight: 48 }
    }
}
