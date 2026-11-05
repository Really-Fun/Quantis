// Приветствие при первом запуске: несколько экранов со свайпом, на каждом
// один выбор — аккаунт Яндекса, где искать, живой или спокойный интерфейс.
// Фон — фирменные пятна циан/розовый/фиолетовый, которые плывут и сдвигаются
// вслед за свайпом, а тон сверху меняется от экрана к экрану.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: root
    color: theme.bg

    readonly property int last: view.count - 1
    readonly property bool atEnd: view.currentIndex === root.last
    // Позиция свайпа в страницах (дробная): для параллакса фона.
    readonly property real progress: view.contentItem.contentX / Math.max(1, view.width)
    readonly property var tints: ["#2A1660", "#4A3A08", "#0A3F4D", "#4D0E33", "#26196B"]
    property color tint: tints[Math.min(view.currentIndex, tints.length - 1)]
    Behavior on tint { ColorAnimation { duration: 800 } }

    function next() {
        if (atEnd)
            finish()
        else
            view.incrementCurrentIndex()
    }
    function back() {
        if (view.currentIndex > 0) {
            view.decrementCurrentIndex()
            return true
        }
        return false
    }
    function finish() {
        Qt.inputMethod.hide()
        leave.start()
    }

    // Уход: экран тает и чуть увеличивается, под ним — приложение.
    ParallelAnimation {
        id: leave
        NumberAnimation { target: root; property: "opacity"; to: 0; duration: 420; easing.type: Easing.InCubic }
        NumberAnimation { target: root; property: "scale"; to: 1.06; duration: 420; easing.type: Easing.InCubic }
        onFinished: app.finishOnboarding()
    }

    // Касания не должны проходить к приложению под приветствием.
    MouseArea { anchors.fill: parent }

    // --- фон -------------------------------------------------------------
    Rectangle {
        anchors.fill: parent
        gradient: Gradient {
            GradientStop { position: 0; color: root.tint }
            GradientStop { position: 0.62; color: theme.bg }
        }
    }
    Repeater {
        model: [
            { color: "00D8F0", x: 0.12, y: 0.16, size: 1.0, period: 15000, depth: 0.10 },
            { color: "FF2A7F", x: 0.92, y: 0.42, size: 0.9, period: 18000, depth: 0.18 },
            { color: "7C4DFF", x: 0.35, y: 0.78, size: 1.2, period: 21000, depth: 0.26 }
        ]
        delegate: Image {
            id: blob
            required property var modelData
            readonly property real base: Math.max(root.width, root.height) * modelData.size
            property real drift: 0
            width: base
            height: base
            x: root.width * modelData.x - base / 2 + drift * root.width * 0.1
               - root.progress * root.width * modelData.depth
            y: root.height * modelData.y - base / 2 + drift * root.height * 0.04
            source: "image://art/blob/" + modelData.color
            sourceSize: Qt.size(256, 256)
            opacity: 0.42
            smooth: true
            Accessible.ignored: true
            SequentialAnimation on drift {
                running: theme.motion && root.visible
                loops: Animation.Infinite
                NumberAnimation { from: -1; to: 1; duration: blob.modelData.period; easing.type: Easing.InOutSine }
                NumberAnimation { from: 1; to: -1; duration: blob.modelData.period; easing.type: Easing.InOutSine }
            }
        }
    }

    // --- экраны ----------------------------------------------------------
    SwipeView {
        id: view
        anchors.top: parent.top
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: footer.top
        // Свайп вперёд не прячет клавиатуру сам: прячем при смене экрана.
        onCurrentIndexChanged: Qt.inputMethod.hide()

        // 0. Привет
        OnboardingPage {
            shown: SwipeView.isCurrentItem
            kicker: "ДОБРО ПОЖАЛОВАТЬ"
            title: "Вся музыка — в одном плеере"
            text: "Яндекс Музыка, YouTube и SoundCloud: ищи, слушай и скачивай из одного места. Настроим всё за минуту."
            artShare: 0.46
            art: [
                Item {
                    anchors.fill: parent
                    // Пульсирующие кольца за знаком.
                    Repeater {
                        model: 2
                        Rectangle {
                            id: ring
                            required property int index
                            anchors.centerIn: parent
                            width: Math.min(parent.width, parent.height) * 0.72
                            height: width
                            radius: width / 2
                            color: "transparent"
                            border.width: 2
                            border.color: index === 0 ? theme.accentCyan : theme.accentPink
                            property real phase: 0
                            scale: 0.7 + phase * 0.5
                            opacity: (1 - phase) * 0.5
                            SequentialAnimation on phase {
                                running: theme.motion && root.visible
                                loops: Animation.Infinite
                                PauseAnimation { duration: ring.index * 1400 }
                                NumberAnimation { from: 0; to: 1; duration: 2800; easing.type: Easing.OutCubic }
                            }
                        }
                    }
                    Image {
                        id: logo
                        anchors.centerIn: parent
                        anchors.verticalCenterOffset: float * 6
                        width: Math.min(parent.width, parent.height) * 0.62
                        height: width
                        fillMode: Image.PreserveAspectFit
                        source: "images/logo.png"
                        smooth: true
                        mipmap: true
                        property real float: 0
                        SequentialAnimation on float {
                            running: theme.motion && root.visible
                            loops: Animation.Infinite
                            NumberAnimation { from: -1; to: 1; duration: 2600; easing.type: Easing.InOutSine }
                            NumberAnimation { from: 1; to: -1; duration: 2600; easing.type: Easing.InOutSine }
                        }
                        Accessible.ignored: true
                    }
                }
            ]
            RowLayout {
                spacing: 8
                Repeater {
                    model: [
                        { name: "Яндекс", color: theme.yandex },
                        { name: "YouTube", color: theme.youtube },
                        { name: "SoundCloud", color: theme.soundcloud }
                    ]
                    Rectangle {
                        required property var modelData
                        implicitHeight: 34
                        implicitWidth: chip.implicitWidth + 34
                        radius: 17
                        color: Qt.rgba(1, 1, 1, 0.06)
                        border.color: Qt.rgba(1, 1, 1, 0.1)
                        Rectangle {
                            x: 12
                            anchors.verticalCenter: parent.verticalCenter
                            width: 8; height: 8; radius: 4
                            color: parent.modelData.color
                        }
                        Text {
                            id: chip
                            x: 26
                            anchors.verticalCenter: parent.verticalCenter
                            text: parent.modelData.name
                            color: theme.text
                            font.family: theme.ui
                            font.pixelSize: 13
                            font.weight: Font.DemiBold
                        }
                    }
                }
            }
        }

        // 1. Аккаунт Яндекса
        OnboardingPage {
            shown: SwipeView.isCurrentItem
            kicker: "ШАГ 1 · АККАУНТ"
            title: app.loggedIn ? "Яндекс Музыка подключена" : "Подключи Яндекс Музыку"
            text: app.loggedIn
                  ? "Моя волна, «Мне нравится», плейлисты и чарт уже на главной."
                  : "Откроются Моя волна, лайки, плейлисты и чарт. Вставь OAuth-токен — тот же, что в Quantis на компьютере. Он хранится только на этом телефоне."
            artShare: 0.3
            art: [
                Item {
                    anchors.fill: parent
                    Rectangle {
                        anchors.centerIn: parent
                        width: Math.min(parent.width, parent.height) * 0.7
                        height: width
                        radius: width / 2
                        color: Qt.rgba(1, 0.8, 0, 0.12)
                        border.width: 2
                        border.color: Qt.rgba(1, 0.8, 0, 0.5)
                        Text {
                            anchors.centerIn: parent
                            text: app.loggedIn ? "✓" : "Я"
                            color: theme.yandex
                            font.family: theme.display
                            font.pixelSize: parent.width * 0.42
                            font.weight: Font.Bold
                        }
                    }
                }
            ]
            InputField {
                id: token
                Layout.fillWidth: true
                visible: !app.loggedIn
                placeholderText: "OAuth-токен"
                echoMode: TextInput.Password
                inputMethodHints: Qt.ImhSensitiveData | Qt.ImhNoPredictiveText
                Accessible.name: "OAuth-токен Яндекс Музыки"
                onAccepted: app.saveToken(text)
            }
            Text {
                Layout.fillWidth: true
                visible: text.length > 0
                text: app.account
                color: app.account.indexOf("не подошёл") >= 0 ? theme.danger
                     : app.loggedIn ? theme.yandex : theme.textDim
                wrapMode: Text.WordWrap
                font.family: theme.ui
                font.pixelSize: 14
                font.weight: app.loggedIn ? Font.DemiBold : Font.Normal
            }
            PillButton {
                Layout.fillWidth: true
                visible: !app.loggedIn
                text: "Подключить"
                variant: "light"
                enabled: token.text.trim().length > 0
                onClicked: app.saveToken(token.text)
            }
        }

        // 2. Где искать
        OnboardingPage {
            shown: SwipeView.isCurrentItem
            kicker: "ШАГ 2 · ПОИСК"
            title: "Где искать в первую очередь?"
            text: "Переключить можно в любой момент прямо на экране поиска."
            artShare: 0.26
            art: [
                Item {
                    anchors.fill: parent
                    // Три точки-источника кружат вокруг лупы.
                    Item {
                        id: orbit
                        anchors.centerIn: parent
                        width: Math.min(parent.width, parent.height) * 0.8
                        height: width
                        RotationAnimation on rotation {
                            running: theme.motion && root.visible
                            loops: Animation.Infinite
                            from: 0; to: 360; duration: 9000
                        }
                        Repeater {
                            model: [theme.yandex, theme.youtube, theme.soundcloud]
                            Rectangle {
                                required property var modelData
                                required property int index
                                width: 16; height: 16; radius: 8
                                color: modelData
                                x: orbit.width / 2 - 8 + Math.cos(index * 2.094) * orbit.width * 0.42
                                y: orbit.height / 2 - 8 + Math.sin(index * 2.094) * orbit.height * 0.42
                            }
                        }
                    }
                    Rectangle {
                        anchors.centerIn: parent
                        width: orbit.width * 0.5
                        height: width
                        radius: width / 2
                        color: Qt.rgba(1, 1, 1, 0.06)
                        border.color: Qt.rgba(1, 1, 1, 0.12)
                        Image {
                            anchors.centerIn: parent
                            source: "icons/search.svg"
                            sourceSize: Qt.size(parent.width * 0.42, parent.width * 0.42)
                            Accessible.ignored: true
                        }
                    }
                }
            ]
            OnboardingCard {
                title: "Яндекс Музыка"
                subtitle: app.loggedIn ? "Треки, альбомы, исполнители" : "Нужен вход — шаг назад"
                letter: "Я"
                tone: theme.yandex
                enabled: app.loggedIn
                selected: app.source === "yandex"
                onClicked: app.setSource("yandex")
            }
            OnboardingCard {
                title: "YouTube"
                subtitle: "Всё, что есть на YouTube Music"
                iconName: "play"
                tone: theme.youtube
                selected: app.source === "youtube"
                onClicked: app.setSource("youtube")
            }
            OnboardingCard {
                title: "SoundCloud"
                subtitle: "Ремиксы, сеты и андерграунд"
                letter: "S"
                tone: theme.soundcloud
                selected: app.source === "soundcloud"
                onClicked: app.setSource("soundcloud")
            }
        }

        // 3. Живой или спокойный
        OnboardingPage {
            shown: SwipeView.isCurrentItem
            kicker: "ШАГ 3 · ВИД"
            title: "Живой или спокойный?"
            text: "Аврора из цветов обложки и пластинка, которая крутится под музыку. Спокойный вид бережёт батарею."
            artShare: 0.32
            art: [
                Item {
                    anchors.fill: parent
                    Vinyl {
                        anchors.centerIn: parent
                        width: Math.min(parent.width, parent.height) * 0.86
                        height: width
                        spinning: true // стоит, если выбран спокойный вид
                        degreesPerSecond: 90
                    }
                }
            ]
            OnboardingCard {
                title: "Живой"
                subtitle: "Аврора, вращение, плавные переходы"
                iconName: "radio"
                tone: theme.accentPink
                selected: app.motion
                onClicked: app.setMotion(true)
            }
            OnboardingCard {
                title: "Спокойный"
                subtitle: "Без фоновой анимации"
                iconName: "moon"
                tone: theme.accentCyan
                selected: !app.motion
                onClicked: app.setMotion(false)
            }
        }

        // 4. Фишки и старт
        OnboardingPage {
            shown: SwipeView.isCurrentItem
            kicker: "ВСЁ ГОТОВО"
            title: "Пара фишек напоследок"
            artShare: 0.2
            art: [
                Image {
                    anchors.centerIn: parent
                    width: Math.min(parent.width, parent.height) * 0.9
                    height: width
                    fillMode: Image.PreserveAspectFit
                    source: "images/logo.png"
                    mipmap: true
                    Accessible.ignored: true
                }
            ]
            Repeater {
                model: [
                    { icon: "music", title: "Крути пластинку пальцем", text: "В плеере — это перемотка, как у диджея" },
                    { icon: "lyrics", title: "Тексты песен в такт", text: "Строка подсвечивается вместе с музыкой" },
                    { icon: "download", title: "Слушай без сети", text: "Скачивай треки и целые плейлисты" },
                    { icon: "moon", title: "Таймер сна", text: "Музыка сама затихнет, когда уснёшь" }
                ]
                RowLayout {
                    id: feature
                    required property var modelData
                    Layout.fillWidth: true
                    spacing: 14
                    Rectangle {
                        Layout.preferredWidth: 40
                        Layout.preferredHeight: 40
                        radius: 12
                        gradient: Gradient {
                            orientation: Gradient.Horizontal
                            GradientStop { position: 0; color: Qt.rgba(0, 0.85, 0.94, 0.25) }
                            GradientStop { position: 1; color: Qt.rgba(1, 0.16, 0.5, 0.25) }
                        }
                        Image {
                            anchors.centerIn: parent
                            source: "icons/" + feature.modelData.icon + ".svg"
                            sourceSize: Qt.size(20, 20)
                            Accessible.ignored: true
                        }
                    }
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 1
                        Text {
                            Layout.fillWidth: true
                            text: feature.modelData.title
                            color: theme.text
                            font.family: theme.ui
                            font.pixelSize: 15
                            font.weight: Font.DemiBold
                            elide: Text.ElideRight
                        }
                        Text {
                            Layout.fillWidth: true
                            text: feature.modelData.text
                            color: theme.textDim
                            font.family: theme.ui
                            font.pixelSize: 13
                            wrapMode: Text.WordWrap
                        }
                    }
                }
            }
        }
    }

    // --- низ: пропустить, точки, далее ----------------------------------
    Item {
        id: footer
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.leftMargin: 16
        anchors.rightMargin: 16
        anchors.bottomMargin: 12
        height: 64

        PillButton {
            anchors.left: parent.left
            anchors.verticalCenter: parent.verticalCenter
            text: "Пропустить"
            variant: "text"
            textColor: theme.textDim
            opacity: root.atEnd ? 0 : 1
            visible: opacity > 0
            Behavior on opacity { NumberAnimation { duration: theme.medium } }
            onClicked: root.finish()
        }

        // Точки: текущая вытягивается в «таблетку» с градиентом.
        Row {
            anchors.centerIn: parent
            anchors.horizontalCenterOffset: root.atEnd ? -(parent.width / 2) + width / 2 + 8 : 0
            Behavior on anchors.horizontalCenterOffset { NumberAnimation { duration: 420; easing.type: Easing.OutCubic } }
            spacing: 6
            Repeater {
                model: view.count
                Rectangle {
                    id: dot
                    required property int index
                    readonly property bool current: index === view.currentIndex
                    width: current ? 24 : 8
                    height: 8
                    radius: 4
                    color: Qt.rgba(1, 1, 1, 0.22)
                    Behavior on width { NumberAnimation { duration: 300; easing.type: Easing.OutCubic } }
                    Rectangle {
                        anchors.fill: parent
                        radius: 4
                        opacity: dot.current ? 1 : 0
                        Behavior on opacity { NumberAnimation { duration: 300 } }
                        gradient: Gradient {
                            orientation: Gradient.Horizontal
                            GradientStop { position: 0; color: theme.accentCyan }
                            GradientStop { position: 1; color: theme.accentPink }
                        }
                    }
                }
            }
        }

        // «Далее» — круглая кнопка; на последнем экране растягивается в «Начать».
        AbstractButton {
            id: nextButton
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            height: 56
            width: root.atEnd ? Math.min(parent.width * 0.62, 240) : 56
            Behavior on width { NumberAnimation { duration: 420; easing.type: Easing.OutCubic } }
            Accessible.role: Accessible.Button
            Accessible.name: root.atEnd ? "Начать" : "Далее"
            onClicked: root.next()
            background: Rectangle {
                radius: height / 2
                gradient: Gradient {
                    orientation: Gradient.Horizontal
                    GradientStop { position: 0; color: theme.accentCyan }
                    GradientStop { position: 1; color: theme.accentPink }
                }
                scale: nextButton.down ? 0.95 : 1
                Behavior on scale { NumberAnimation { duration: theme.fast } }
            }
            contentItem: Item {
                Image {
                    anchors.centerIn: parent
                    opacity: root.atEnd ? 0 : 1
                    Behavior on opacity { NumberAnimation { duration: 200 } }
                    source: "icons/chevron-right.svg"
                    sourceSize: Qt.size(26, 26)
                    Accessible.ignored: true
                }
                Text {
                    anchors.centerIn: parent
                    opacity: root.atEnd ? 1 : 0
                    Behavior on opacity { NumberAnimation { duration: 300 } }
                    text: "Начать слушать"
                    color: "#0B0D12"
                    font.family: theme.ui
                    font.pixelSize: 16
                    font.weight: Font.Bold
                }
            }
        }
    }
}
