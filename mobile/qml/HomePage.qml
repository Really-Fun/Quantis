// Главная: логотип и аккаунт, карточка «Сейчас играет» (без трека — «Моя волна»
// или «Найти музыку»), настроения волны, «Недавно играло», «Твоя медиатека»
// (Мне нравится, свои плейлисты и плейлисты Яндекса), чарт Яндекса, новые
// релизы и «Недавние запросы» чипами. Страницы открываются в стеке вкладки.
import QtQuick
import QtQuick.Controls
import QtQuick.Controls.Material
import QtQuick.Layouts

Flickable {
    id: page
    signal searchRequested(string query)
    signal playerRequested()
    signal accountRequested()

    function open(kind, ref, title) { window.openPage(page.StackView.view, kind, ref, title) }
    // Плитки «Твоей медиатеки»: Мне нравится, свои плейлисты, плейлисты Яндекса.
    readonly property var libraryTiles: {
        var tiles = []
        if (app.loggedIn && app.yandexLiked.count > 0)
            tiles.push({ title: "Мне нравится", subtitle: app.yandexLiked.count + " · Яндекс",
                         icon: "heart-filled", kind: "liked", ref: "" })
        var local = app.localPlaylists
        for (var i = 0; i < local.length; i++)
            tiles.push({ title: local[i].name, subtitle: "На телефоне",
                         cover: local[i].cover ? decodeURIComponent(local[i].cover) : "",
                         kind: "local", ref: local[i].id })
        var remote = app.loggedIn ? app.yandexPlaylists : []
        for (var j = 0; j < remote.length; j++)
            tiles.push({ title: remote[j].title, subtitle: remote[j].owner || "Яндекс",
                         cover: remote[j].cover, kind: "playlist", ref: remote[j].uid + ":" + remote[j].kind })
        return tiles
    }
    function refreshData() {
        if (app.loggedIn) {
            app.refreshHome()
            app.refreshYandexLibrary()
        }
    }
    Component.onCompleted: refreshData()
    onVisibleChanged: if (visible) refreshData()

    contentHeight: column.implicitHeight + 32
    // Только вертикаль: без contentWidth ширину считали по детям, и шире
    // экрана (аврора, тени) страница ловила горизонтальный жест вместо прокрутки.
    contentWidth: width
    flickableDirection: Flickable.VerticalFlick
    clip: true
    boundsBehavior: Flickable.DragOverBounds

    // Подсветка верха страницы цветами играющего трека — та же аврора, что в
    // плеере, только тише; без трека её нет.
    Aurora {
        width: page.width
        height: 560
        y: -page.contentY * 0.4 // лёгкий параллакс при прокрутке
        visible: app.hasTrack
        opacity: 0.8
        topFade: 96
        fadeOut: true
        active: app.playing && !app.loading
    }

    ColumnLayout {
        id: column
        width: page.width
        spacing: 24

        // Шапка: логотип и вход в аккаунт.
        RowLayout {
            Layout.fillWidth: true
            Layout.leftMargin: theme.gutter
            Layout.rightMargin: theme.gutter - 8
            Layout.topMargin: 12
            Text {
                Layout.fillWidth: true
                text: "QUANTIS"
                color: theme.text
                font.family: theme.display
                font.pixelSize: 20
                font.weight: Font.Bold
                font.letterSpacing: 3
            }
            IconButton {
                iconName: "user"
                label: app.loggedIn ? "Аккаунт Яндекс Музыки" : "Войти в Яндекс Музыку"
                onClicked: page.accountRequested()
            }
        }

        // Главная карточка: играющий трек или приглашение к поиску.
        Rectangle {
            id: hero
            Layout.fillWidth: true
            Layout.leftMargin: theme.gutter
            Layout.rightMargin: theme.gutter
            Layout.preferredHeight: 168
            radius: theme.radius + 4
            // Без трека — фирменный градиент; с треком — тёмное стекло поверх авроры.
            gradient: app.hasTrack ? null : brand
            color: app.hasTrack ? Qt.rgba(0.08, 0.09, 0.12, 0.55) : "transparent"
            border.color: app.hasTrack ? Qt.rgba(1, 1, 1, 0.08) : "transparent"
            Gradient {
                id: brand
                orientation: Gradient.Horizontal
                GradientStop { position: 0; color: Qt.darker(theme.accent, 1.5) }
                GradientStop { position: 1; color: Qt.darker(theme.accentPink, 2.3) }
            }

            // Обложка с пластинкой справа, пока что-то играет.
            Item {
                id: heroArt
                visible: app.hasTrack
                anchors.right: parent.right
                anchors.rightMargin: 16
                anchors.verticalCenter: parent.verticalCenter
                width: 132
                height: 104
                Vinyl {
                    x: 36; y: 2
                    width: 100; height: 100
                    cover: app.cover
                    spinning: app.playing && !app.loading
                }
                CoverArt {
                    width: 104; height: 104
                    radius: 14
                    seed: app.title
                    cover: app.cover
                }
            }

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 20
                anchors.rightMargin: app.hasTrack ? heroArt.width + 28 : 20
                spacing: 6
                Text {
                    text: app.hasTrack
                          ? (app.waveActive ? (app.waveName === "Моя волна" ? "МОЯ ВОЛНА"
                                             : "МОЯ ВОЛНА · " + app.waveName.toUpperCase())
                                          : "СЕЙЧАС ИГРАЕТ")
                          : (app.loggedIn ? "МОЯ ВОЛНА" : "ЯНДЕКС · YOUTUBE · SOUNDCLOUD")
                    color: Qt.rgba(1, 1, 1, 0.7)
                    font.family: theme.ui
                    font.pixelSize: 12
                    font.weight: Font.Bold
                    font.letterSpacing: 1.6
                }
                Text {
                    Layout.fillWidth: true
                    text: app.hasTrack ? app.title
                          : (app.loggedIn ? "Поток под твой вкус" : "Что послушаем?")
                    color: theme.text
                    font.family: theme.display
                    font.pixelSize: 20
                    font.weight: Font.DemiBold
                    wrapMode: Text.WordWrap
                    // С треком — одна строка: иначе с исполнителем и кнопкой
                    // не помещалось в карточку.
                    maximumLineCount: app.hasTrack ? 1 : 2
                    elide: Text.ElideRight
                }
                Text {
                    Layout.fillWidth: true
                    visible: app.hasTrack
                    text: app.artist
                    color: Qt.rgba(1, 1, 1, 0.75)
                    font.family: theme.ui
                    font.pixelSize: 14
                    elide: Text.ElideRight
                }
                Item { Layout.fillHeight: true }
                PillButton {
                    text: app.hasTrack ? "Открыть плеер"
                          : (app.waveLoading ? "Запускаем…" : (app.loggedIn ? "Слушать волну" : "Найти музыку"))
                    variant: "light"
                    enabled: !app.waveLoading
                    onClicked: {
                        if (app.hasTrack) page.playerRequested()
                        else if (app.loggedIn) app.startWave("", "Моя волна")
                        else page.searchRequested("")
                    }
                }
            }
        }

        // «Моя волна» по настроению: касание запускает волну с этими сидами.
        ColumnLayout {
            Layout.fillWidth: true
            visible: app.loggedIn
            spacing: 12
            RowLayout {
                Layout.leftMargin: theme.gutter
                Layout.rightMargin: theme.gutter
                Text {
                    Layout.fillWidth: true
                    text: "Моя волна"
                    color: theme.text
                    font.family: theme.display
                    font.pixelSize: 18
                    font.weight: Font.DemiBold
                }
                BusyIndicator {
                    implicitWidth: 28; implicitHeight: 28
                    running: app.waveLoading
                    visible: running
                }
            }
            ListView {
                Layout.fillWidth: true
                Layout.preferredHeight: 44
                orientation: ListView.Horizontal
                spacing: 8
                leftMargin: theme.gutter
                rightMargin: theme.gutter
                clip: true
                boundsBehavior: Flickable.DragOverBounds
                model: [{ name: "Моя волна", seeds: "", color: "#7C4DFF" }].concat(app.moods)
                delegate: AbstractButton {
                    id: mood
                    required property var modelData
                    readonly property bool active: app.waveActive && app.waveName === modelData.name
                    height: 40
                    width: moodRow.implicitWidth + 28
                    enabled: !app.waveLoading
                    Accessible.name: "Волна: " + modelData.name
                    onClicked: app.startWave(modelData.seeds, modelData.name)
                    background: Rectangle {
                        radius: height / 2
                        color: mood.active ? Qt.rgba(1, 1, 1, 0.12) : "transparent"
                        border.color: mood.active ? mood.modelData.color : theme.stroke
                        border.width: mood.active ? 2 : 1
                        scale: mood.down ? 0.96 : 1
                        Behavior on scale { NumberAnimation { duration: theme.fast } }
                    }
                    contentItem: Row {
                        id: moodRow
                        spacing: 8
                        leftPadding: 14
                        Rectangle { // цвет настроения — точкой, рядом с подписью
                            anchors.verticalCenter: parent.verticalCenter
                            width: 10; height: 10; radius: 5
                            color: mood.modelData.color
                        }
                        Text {
                            anchors.verticalCenter: parent.verticalCenter
                            text: mood.modelData.name
                            color: theme.text
                            font.family: theme.ui
                            font.pixelSize: 14
                            font.weight: Font.DemiBold
                        }
                    }
                }
            }
        }

        // Недавно играло: лента обложек, касание — играть с этого места.
        ColumnLayout {
            Layout.fillWidth: true
            visible: app.history.count > 0
            spacing: 12
            Text {
                Layout.leftMargin: theme.gutter
                text: "Недавно играло"
                color: theme.text
                font.family: theme.display
                font.pixelSize: 18
                font.weight: Font.DemiBold
            }
            ListView {
                Layout.fillWidth: true
                Layout.preferredHeight: 196
                orientation: ListView.Horizontal
                spacing: 12
                leftMargin: theme.gutter
                rightMargin: theme.gutter
                clip: true
                model: app.history
                boundsBehavior: Flickable.DragOverBounds
                delegate: ItemDelegate {
                    id: tile
                    required property int index
                    required property string title
                    required property string artist
                    required property string cover
                    width: 140
                    height: 196
                    padding: 0
                    Accessible.name: title + ", " + artist
                    onClicked: app.playHistory(index)
                    background: Item {}
                    contentItem: ColumnLayout {
                        spacing: 8
                        CoverArt {
                            Layout.preferredWidth: 140
                            Layout.preferredHeight: 140
                            radius: 14
                            seed: tile.title
                            cover: tile.cover
                            scale: tile.down ? 0.97 : 1
                            Behavior on scale { NumberAnimation { duration: theme.fast } }
                        }
                        Text {
                            Layout.fillWidth: true
                            text: tile.title
                            color: theme.text
                            font.family: theme.ui
                            font.pixelSize: 14
                            font.weight: Font.DemiBold
                            elide: Text.ElideRight
                        }
                        Text {
                            Layout.fillWidth: true
                            text: tile.artist
                            color: theme.textDim
                            font.family: theme.ui
                            font.pixelSize: 12
                            elide: Text.ElideRight
                        }
                    }
                }
            }
        }

        CoverRibbon {
            title: "Твоя медиатека"
            model: page.libraryTiles
            loading: app.loggedIn && app.yandexLibraryLoading
            onPicked: function (item) { page.open(item.kind, item.ref, item.title) }
        }

        // Чарт Яндекса: пять строк, остальное — «Все».
        ColumnLayout {
            Layout.fillWidth: true
            visible: app.loggedIn && (app.homeChart.count > 0 || app.homeLoading)
            spacing: 4
            RowLayout {
                Layout.fillWidth: true
                Layout.leftMargin: theme.gutter
                Layout.rightMargin: theme.gutter - 8
                Text {
                    Layout.fillWidth: true
                    text: "Чарт Яндекса"
                    color: theme.text
                    font.family: theme.display
                    font.pixelSize: 18
                    font.weight: Font.DemiBold
                }
                PillButton {
                    text: "Все"
                    variant: "text"
                    compact: true
                    onClicked: page.open("chart", "", "Чарт")
                }
            }
            // Заглушки строк, пока чарт грузится впервые.
            Repeater {
                model: app.homeChart.count === 0 ? 5 : 0
                delegate: RowLayout {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 72
                    Layout.leftMargin: theme.gutter
                    Layout.rightMargin: theme.gutter
                    spacing: 12
                    Rectangle { Layout.preferredWidth: 52; Layout.preferredHeight: 52; radius: 10; color: theme.surfaceHigh }
                    ColumnLayout {
                        spacing: 8
                        Rectangle { Layout.preferredWidth: 160; Layout.preferredHeight: 12; radius: 6; color: theme.surface }
                        Rectangle { Layout.preferredWidth: 100; Layout.preferredHeight: 10; radius: 5; color: theme.surface }
                    }
                    Item { Layout.fillWidth: true }
                }
            }
            Repeater {
                model: app.homeChart
                delegate: TrackRow {
                    listName: "homeChart"
                    visible: index < 5
                    Layout.fillWidth: true
                    Layout.preferredHeight: visible ? 72 : 0
                    current: app.hasTrack && title === app.title && artist === app.artist
                }
            }
        }

        CoverRibbon {
            title: "Новые релизы"
            model: app.loggedIn ? app.homeReleases : []
            loading: app.loggedIn && app.homeLoading
            onPicked: function (item) { page.open("album", item.id, item.title) }
        }

        // Недавние запросы: касание повторяет поиск.
        ColumnLayout {
            Layout.fillWidth: true
            Layout.leftMargin: theme.gutter
            Layout.rightMargin: theme.gutter
            visible: app.recentQueries.length > 0
            spacing: 12
            Text {
                text: "Недавние запросы"
                color: theme.text
                font.family: theme.display
                font.pixelSize: 18
                font.weight: Font.DemiBold
            }
            Flow {
                Layout.fillWidth: true
                spacing: 8
                Repeater {
                    model: app.recentQueries
                    delegate: PillButton {
                        required property string modelData
                        text: modelData
                        variant: "outlined"
                        compact: true
                        onClicked: page.searchRequested(modelData)
                    }
                }
            }
        }

        // Первый запуск: ни истории, ни запросов.
        Text {
            Layout.fillWidth: true
            Layout.leftMargin: theme.gutter
            Layout.rightMargin: theme.gutter
            visible: app.history.count === 0 && app.recentQueries.length === 0
            text: app.loggedIn
                  ? "Найди трек во вкладке «Поиск» — здесь появится то, что ты слушал."
                  : "Войди в Яндекс Музыку (значок справа вверху) или ищи на YouTube без входа."
            color: theme.textDim
            wrapMode: Text.WordWrap
            font.family: theme.ui
            font.pixelSize: 14
        }
    }
}
