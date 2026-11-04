// Текст песни. Синхронный (LRC) — текущая строка подсвечена, список сам
// держит её по центру (после ручной прокрутки — через 3 с); касание строки
// перематывает к ней. Без времени — просто текст.
import QtQuick
import QtQuick.Controls
import QtQuick.Controls.Material
import QtQuick.Layouts

Drawer {
    id: sheet
    edge: Qt.BottomEdge
    interactive: opened
    dragMargin: 0
    modal: true
    Overlay.modal: Rectangle { color: Qt.rgba(0, 0, 0, 0.55) }

    onOpened: app.setLyricsOpen(true)
    onClosed: app.setLyricsOpen(false)

    background: Rectangle {
        color: theme.surface
        radius: 24
        Rectangle {
            anchors.bottom: parent.bottom
            width: parent.width; height: 24
            color: parent.color
        }
    }

    // Индекс строки, которая звучит сейчас: последняя с t <= позиции.
    readonly property int currentLine: {
        if (!app.lyricsSynced)
            return -1
        var lines = app.lyricsLines, pos = app.position + 250 // чуть заранее
        var lo = 0, hi = lines.length - 1, found = -1
        while (lo <= hi) {
            var mid = (lo + hi) >> 1
            if (lines[mid].t <= pos) { found = mid; lo = mid + 1 } else hi = mid - 1
        }
        return found
    }
    property bool follow: true
    onCurrentLineChanged: if (follow && opened && currentLine >= 0)
        list.positionViewAtIndex(currentLine, ListView.Center)
    Timer { id: resume; interval: 3000; onTriggered: sheet.follow = true }

    ColumnLayout {
        anchors.fill: parent
        anchors.bottomMargin: sheet.bottomPadding
        spacing: 0

        Rectangle {
            Layout.alignment: Qt.AlignHCenter
            Layout.topMargin: 10
            width: 36; height: 4; radius: 2
            color: theme.stroke
        }
        RowLayout {
            Layout.fillWidth: true
            Layout.leftMargin: theme.gutter
            Layout.rightMargin: 4
            Layout.topMargin: 8
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 2
                Text {
                    Layout.fillWidth: true
                    text: app.title || "Текст"
                    color: theme.text
                    font.family: theme.display
                    font.pixelSize: 20
                    font.weight: Font.DemiBold
                    elide: Text.ElideRight
                }
                Text {
                    text: app.lyricsSource ? "Текст: " + app.lyricsSource : app.artist
                    color: theme.textDim
                    font.family: theme.ui
                    font.pixelSize: 13
                }
            }
            IconButton { iconName: "x"; label: "Закрыть текст"; onClicked: sheet.close() }
        }

        ListView {
            id: list
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.topMargin: 8
            clip: true
            model: app.lyricsLines
            spacing: app.lyricsSynced ? 6 : 2
            topMargin: 24
            bottomMargin: height / 2
            highlightMoveDuration: 400
            onMovementStarted: { sheet.follow = false; resume.stop() }
            onMovementEnded: resume.restart()
            delegate: Text {
                required property var modelData
                required property int index
                readonly property bool now: index === sheet.currentLine
                width: ListView.view.width
                leftPadding: theme.gutter
                rightPadding: theme.gutter
                text: modelData.text || "♪"
                wrapMode: Text.WordWrap
                color: now ? app.accent : (app.lyricsSynced && index < sheet.currentLine ? theme.textDim : theme.text)
                opacity: !app.lyricsSynced || now ? 1 : 0.6
                font.family: theme.ui
                font.pixelSize: app.lyricsSynced ? 22 : 17
                font.weight: app.lyricsSynced ? Font.Bold : Font.Normal
                lineHeight: 1.15
                Behavior on color { ColorAnimation { duration: theme.fast } }
                TapHandler {
                    enabled: app.lyricsSynced && modelData.t >= 0
                    onTapped: { app.seek(modelData.t); sheet.follow = true }
                }
                Accessible.role: Accessible.StaticText
                Accessible.name: text
            }
            ScrollIndicator.vertical: ScrollIndicator {}

            BusyIndicator {
                anchors.centerIn: parent
                running: app.lyricsState === "loading"
                visible: running
            }
            Text {
                anchors.centerIn: parent
                width: parent.width - 2 * theme.gutter
                visible: app.lyricsState === "none" || app.lyricsState === "error"
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.WordWrap
                text: app.lyricsState === "error" ? "Текст не загрузился — нет сети?"
                                                   : "Текста для этого трека не нашлось"
                color: theme.textDim
                font.family: theme.ui
                font.pixelSize: 15
            }
        }
    }
}
