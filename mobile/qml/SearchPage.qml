// Поиск: поле, выбор источника, выдача. У Яндекса выдача по всему: лучший
// результат, треки (5 + «Все»), исполнители, альбомы, плейлисты — касание
// открывает страницу в стеке вкладки. У YouTube и SoundCloud — только треки.
// Пустое состояние и ошибки — текстом под полем, загрузка — индикатором.
import QtQuick
import QtQuick.Controls
import QtQuick.Controls.Material
import QtQuick.Layouts

Item {
    id: page
    readonly property bool rich: app.searchArtists.length + app.searchAlbums.length
                                 + app.searchPlaylists.length > 0
    function open(kind, ref, title) { window.openPage(page.StackView.view, kind, ref, title) }
    function openBest() {
        var best = app.searchBest
        if (best.type === "artist") open("artist", best.item.id, best.item.name)
        else if (best.type === "album") open("album", best.item.id, best.item.title)
        else if (best.type === "playlist") open("playlist", best.item.uid + ":" + best.item.kind, best.item.title)
        else if (best.type === "track") app.playFrom("results", 0)
    }

    Component {
        id: allTracksPage
        TrackListPage {
            title: "Треки"
            listName: "results"
            model: app.results
            onBack: page.StackView.view.pop()
        }
    }

    // Поиск снаружи (недавний запрос на главной).
    function runQuery(text) {
        query.text = text
        typing.stop()
        app.search(text)
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        Text {
            Layout.leftMargin: theme.gutter
            Layout.topMargin: 20
            text: "Поиск"
            color: theme.text
            font.family: theme.display
            font.pixelSize: 26
            font.weight: Font.DemiBold
        }

        InputField {
            id: query
            Layout.fillWidth: true
            Layout.leftMargin: theme.gutter
            Layout.rightMargin: theme.gutter
            Layout.topMargin: 16
            iconName: "search"
            placeholderText: "Трек, артист или альбом"
            inputMethodHints: Qt.ImhNoPredictiveText
            EnterKey.type: Qt.EnterKeySearch
            // Enter с русской клавиатуры на Android доходил не всегда, и поиск
            // молчал: ищем и по мере ввода, через 0,9 с после последней буквы.
            // displayText — с текстом, который клавиатура ещё не зафиксировала.
            // Печатают дальше — ответ на прежний запрос уже не нужен: применять
            // его (перестройка выдачи) значит подвесить ввод под пальцами.
            onDisplayTextChanged: {
                typing.restart()
                app.searchStale()
            }
            onAccepted: {
                typing.stop()
                Qt.inputMethod.commit()
                app.search(text)
            }
            Accessible.name: "Поиск музыки"
            Timer {
                id: typing
                interval: 900
                onTriggered: if (query.displayText.trim().length >= 2) app.searchAsYouType(query.displayText)
            }
        }

        Flow { // на узком экране чипы переносятся
            Layout.fillWidth: true
            Layout.leftMargin: theme.gutter
            Layout.rightMargin: theme.gutter
            Layout.topMargin: 12
            spacing: 8
            Repeater {
                model: [{ id: "yandex", label: "Яндекс Музыка" }, { id: "youtube", label: "YouTube" },
                        { id: "soundcloud", label: "SoundCloud" }]
                delegate: PillButton {
                    required property var modelData
                    text: modelData.label
                    variant: app.source === modelData.id ? "filled" : "outlined"
                    compact: true
                    Accessible.checked: app.source === modelData.id
                    onClicked: {
                        app.setSource(modelData.id)
                        if (query.text.trim().length > 0 && app.source === modelData.id)
                            app.search(query.text)
                    }
                }
            }
        }

        Text {
            Layout.fillWidth: true
            Layout.leftMargin: theme.gutter
            Layout.rightMargin: theme.gutter
            Layout.topMargin: 8
            visible: text.length > 0
            text: app.status
            color: theme.textDim
            wrapMode: Text.WordWrap
            font.family: theme.ui
            font.pixelSize: 14
        }

        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.topMargin: 8

            // Выдача Яндекса по всему.
            Flickable {
                id: richView
                anchors.fill: parent
                // старая выдача остаётся на месте, пока ищется новая — без мигания
                visible: page.rich
                clip: true
                contentHeight: richColumn.implicitHeight + 24
                // Только вертикаль: без contentWidth ширину считали по детям, и шире
                // экрана (аврора, тени) страница ловила горизонтальный жест вместо прокрутки.
                contentWidth: width
                flickableDirection: Flickable.VerticalFlick
                boundsBehavior: Flickable.DragOverBounds
                ScrollIndicator.vertical: ScrollIndicator {}
                Connections { target: app; function onSearchExtrasChanged() { richView.contentY = 0 } }

                ColumnLayout {
                    id: richColumn
                    width: richView.width
                    spacing: 20

                    // Лучший результат — крупной карточкой.
                    ItemDelegate {
                        id: bestCard
                        readonly property var best: app.searchBest
                        readonly property var item: best.item || ({})
                        readonly property bool isTrack: best.type === "track"
                        readonly property string label: isTrack ? (list.count > 0 ? app.results.titleAt(0) : "")
                                                       : (item.name || item.title || "")
                        visible: !!best.type && label.length > 0
                        Layout.fillWidth: true
                        Layout.leftMargin: theme.gutter
                        Layout.rightMargin: theme.gutter
                        Layout.topMargin: 8
                        height: 112
                        padding: 12
                        Accessible.name: "Лучший результат: " + label
                        onClicked: page.openBest()
                        background: Rectangle {
                            radius: theme.radius
                            color: bestCard.down ? theme.surfaceHigh : theme.surface
                            border.color: theme.stroke
                        }
                        contentItem: RowLayout {
                            spacing: 14
                            CoverArt {
                                Layout.preferredWidth: 88
                                Layout.preferredHeight: 88
                                radius: bestCard.best.type === "artist" ? 44 : 12
                                seed: bestCard.label
                                cover: bestCard.isTrack ? (list.count > 0 ? app.results.coverAt(0) : "")
                                       : (bestCard.item.cover ? encodeURIComponent(bestCard.item.cover) : "")
                            }
                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 4
                                Text {
                                    text: ({ artist: "ИСПОЛНИТЕЛЬ", album: "АЛЬБОМ", playlist: "ПЛЕЙЛИСТ",
                                             track: "ТРЕК" })[bestCard.best.type] || ""
                                    color: theme.accent
                                    font.family: theme.ui
                                    font.pixelSize: 11
                                    font.weight: Font.Bold
                                    font.letterSpacing: 0.8
                                }
                                Text {
                                    Layout.fillWidth: true
                                    text: bestCard.label
                                    color: theme.text
                                    font.family: theme.display
                                    font.pixelSize: 20
                                    font.weight: Font.DemiBold
                                    elide: Text.ElideRight
                                }
                                Text {
                                    Layout.fillWidth: true
                                    visible: text.length > 0
                                    text: bestCard.isTrack ? (list.count > 0 ? app.results.artistAt(0) : "")
                                          : (bestCard.item.subtitle || bestCard.item.owner || "")
                                    color: theme.textDim
                                    font.family: theme.ui
                                    font.pixelSize: 13
                                    elide: Text.ElideRight
                                }
                            }
                            Image {
                                source: bestCard.isTrack ? "icons/play.svg" : "icons/chevron-right.svg"
                                sourceSize: Qt.size(24, 24)
                                opacity: 0.7
                                Accessible.ignored: true
                            }
                        }
                    }

                    // Треки: первые пять, остальные — «Все».
                    ColumnLayout {
                        Layout.fillWidth: true
                        visible: list.count > 0
                        spacing: 4
                        RowLayout {
                            Layout.fillWidth: true
                            Layout.leftMargin: theme.gutter
                            Layout.rightMargin: theme.gutter - 8
                            Text {
                                Layout.fillWidth: true
                                text: "Треки"
                                color: theme.text
                                font.family: theme.display
                                font.pixelSize: 18
                                font.weight: Font.DemiBold
                            }
                            PillButton {
                                visible: list.count > 5
                                text: "Все"
                                variant: "text"
                                compact: true
                                onClicked: page.StackView.view.push(allTracksPage)
                            }
                        }
                        Repeater {
                            model: app.results
                            delegate: TrackRow {
                                listName: "results"
                                visible: index < 5
                                Layout.fillWidth: true
                                Layout.preferredHeight: visible ? 72 : 0
                                current: app.hasTrack && title === app.title && artist === app.artist
                            }
                        }
                    }
                    CoverRibbon {
                        title: "Исполнители"
                        round: true
                        tile: 112
                        model: app.searchArtists
                        onPicked: function (item) { page.open("artist", item.id, item.name) }
                    }
                    CoverRibbon {
                        title: "Альбомы"
                        model: app.searchAlbums
                        onPicked: function (item) { page.open("album", item.id, item.title) }
                    }
                    CoverRibbon {
                        title: "Плейлисты"
                        model: app.searchPlaylists
                        onPicked: function (item) { page.open("playlist", item.uid + ":" + item.kind, item.title) }
                    }
                }
            }

            // YouTube и SoundCloud (и Яндекс без выдачи по всему) — список треков.
            ListView {
                id: list
                anchors.fill: parent
                visible: !page.rich
                clip: true
                model: app.results
                boundsBehavior: Flickable.DragOverBounds
                delegate: TrackRow {
                    listName: "results"
                    current: app.hasTrack && title === app.title && artist === app.artist
                }
                ScrollIndicator.vertical: ScrollIndicator {}
            }

            // Большая крутилка — только когда показать нечего; при выдаче на
            // экране — тонкая полоска сверху.
            BusyIndicator {
                anchors.centerIn: parent
                running: app.searching && list.count === 0 && !page.rich
                visible: running
            }
            ProgressBar {
                anchors.top: parent.top
                anchors.left: parent.left
                anchors.right: parent.right
                indeterminate: true
                visible: app.searching && (list.count > 0 || page.rich)
                Material.accent: theme.accent
            }

            ColumnLayout {
                anchors.centerIn: parent
                width: parent.width - 2 * theme.gutter
                visible: !app.searching && list.count === 0 && !page.rich && app.status.length === 0
                spacing: 8
                Image {
                    Layout.alignment: Qt.AlignHCenter
                    source: "icons/search.svg"
                    sourceSize: Qt.size(40, 40)
                    opacity: 0.35
                    Accessible.ignored: true
                }
                Text {
                    Layout.fillWidth: true
                    horizontalAlignment: Text.AlignHCenter
                    text: app.source === "yandex"
                          ? "Ищи по названию или артисту в Яндекс Музыке"
                          : app.source === "soundcloud" ? "Ищи по названию или артисту на SoundCloud"
                          : "Ищи по названию или артисту на YouTube"
                    color: theme.textDim
                    wrapMode: Text.WordWrap
                    font.family: theme.ui
                    font.pixelSize: 15
                }
            }
        }
    }
}
