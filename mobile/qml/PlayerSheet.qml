// Полноэкранный плеер: выезжает снизу, свайп вниз или «⌄» сворачивают.
// Фишка — живая пластинка: выезжает из-под обложки и крутится, пока играет,
// её можно «скретчить» пальцем; за ней аврора из цветов обложки, которая
// дышит вместе с пластинкой и вспыхивает при скретче.
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

    readonly property bool live: app.playing && !app.loading

    background: Rectangle {
        color: theme.bg
        Aurora {
            anchors.fill: parent
            visible: sheet.position > 0
            active: sheet.live
            flash: record.scratching ? 1.45 : 1
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

        // «Дека»: обложка-конверт и пластинка, выезжающая справа.
        Item {
            id: deck
            readonly property real coverSize: Math.min((sheet.width - 48) / 1.42, sheet.height * 0.4)
            Layout.alignment: Qt.AlignHCenter
            Layout.preferredWidth: coverSize * 1.42
            Layout.preferredHeight: coverSize

            Vinyl {
                id: record
                width: deck.coverSize * 0.95
                height: width
                y: (deck.coverSize - height) / 2
                // Выезжает так, чтобы показалась часть «яблока» с обложкой.
                x: sheet.live ? deck.coverSize * 0.45 : deck.coverSize * 0.03
                Behavior on x { NumberAnimation { duration: 560; easing.type: Easing.OutCubic } }
                cover: app.cover
                spinning: sheet.live && sheet.opened
                scratchable: true
                exposedFromX: deck.coverSize - x
            }

            Rectangle { // мягкая тень под конвертом
                x: 6; y: 10
                width: deck.coverSize; height: width
                radius: 22
                color: "#000000"
                opacity: 0.35
            }
            CoverArt {
                id: cover
                width: deck.coverSize
                height: width
                radius: 20
                glyph: 0.3
                seed: app.title
                cover: app.cover
                // Свайп по обложке: влево — следующий трек, вправо — предыдущий
                // (кнопки ниже делают то же).
                DragHandler {
                    id: swipe
                    target: null
                    xAxis.enabled: true
                    yAxis.enabled: false
                    onActiveChanged: {
                        if (active) return
                        var dx = centroid.position.x - centroid.pressPosition.x
                        if (dx < -64) app.next()
                        else if (dx > 64) app.previous()
                    }
                }
            }
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
