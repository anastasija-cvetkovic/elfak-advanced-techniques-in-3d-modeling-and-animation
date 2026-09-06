--------------------------------------------------------------------------------
-- export_ascii.ms
-- Konverzija 3ds Max scene u ASCII format iz zadatka:
--
--     <broj tacaka>
--     <broj trouglova>
--     x y z          (po jedan red za svaku tacku)
--     a b c          (po jedan red za svaki trougao, indeksi 0-based)
--
-- Radi u DVA rezima:
--
--  1) HEADLESS — kada su postavljene promenljive okoline MAX_INPUT i MAX_OUTPUT.
--     Ucitava .max fajl, exportuje i zatvara Max. Bez ijednog dijaloga.
--     Ovako ga zove core/converter.py::export_from_max_headless.
--
--  2) INTERAKTIVNO — kada promenljive nisu postavljene. Exportuje trenutnu
--     scenu i pita korisnika gde da sacuva.
--
-- Sva geometrija u sceni se spaja u JEDNU listu tacaka i trouglova, sa
-- pomeranjem indeksa. To odgovara profesorovim primerima: elisa.txt je jedan
-- fajl koji sadrzi 4 nepovezane komponente (glavcina + tri lopatice).
--------------------------------------------------------------------------------

fn collectMeshObjects = (
    local result = #()
    for o in geometry do (
        if (isDeleted o) then continue
        if (canConvertTo o TriMeshGeometry) then append result o
    )
    result
)

fn exportSceneToASCII outPath = (
    local objs = collectMeshObjects()
    if objs.count == 0 then (
        format "GRESKA: u sceni nema geometrije koja se moze konvertovati u mesh.\n"
        return false
    )

    -- snapshotAsMesh primenjuje transformaciju objekta, pa su koordinate
    -- vec u svetskom prostoru — isto kao u profesorovim primerima.
    local meshes   = #()
    local totalV   = 0
    local totalF   = 0
    for o in objs do (
        local m = snapshotAsMesh o
        append meshes m
        totalV += m.numverts
        totalF += m.numfaces
    )

    local f = openFile outPath mode:"w"
    if f == undefined then (
        for m in meshes do delete m
        format "GRESKA: ne mogu da otvorim izlazni fajl: %\n" outPath
        return false
    )

    format "%\n" totalV to:f
    format "%\n" totalF to:f

    -- 1) sve tacke, redom po objektima
    for m in meshes do (
        for i = 1 to m.numverts do (
            local v = getVert m i
            format "% % %\n" v.x v.y v.z to:f
        )
    )

    -- 2) svi trouglovi; MAXScript indeksira od 1, format iz zadatka od 0,
    --    a svaki sledeci objekat se pomera za broj vec ispisanih tacaka.
    local offset = 0
    for m in meshes do (
        for i = 1 to m.numfaces do (
            local fc = getFace m i
            format "% % %\n" \
                ((fc.x as integer) - 1 + offset) \
                ((fc.y as integer) - 1 + offset) \
                ((fc.z as integer) - 1 + offset) to:f
        )
        offset += m.numverts
    )

    closeFile f
    for m in meshes do delete m

    format "OK: % objekata, % tacaka, % trouglova -> %\n" \
        objs.count totalV totalF outPath
    true
)

--------------------------------------------------------------------------------
-- Ulazna tacka
--------------------------------------------------------------------------------

local inPath  = systemTools.getEnvVariable "MAX_INPUT"
local outPath = systemTools.getEnvVariable "MAX_OUTPUT"

if outPath != undefined and outPath != "" then (
    -- ── HEADLESS ──────────────────────────────────────────────────────────
    local ok = false
    if inPath != undefined and inPath != "" then (
        if not (doesFileExist inPath) then
            format "GRESKA: ulazni .max fajl ne postoji: %\n" inPath
        else if not (loadMaxFile inPath quiet:true) then
            format "GRESKA: loadMaxFile nije uspeo: %\n" inPath
        else
            ok = exportSceneToASCII outPath
    )
    else
        -- MAX_OUTPUT bez MAX_INPUT: exportuj scenu koja je vec ucitana
        ok = exportSceneToASCII outPath

    -- Ako export nije uspeo, izlazni fajl ne postoji i Python strana
    -- (converter.py) to prijavljuje kao gresku.
    quitMax #noPrompt
)
else (
    -- ── INTERAKTIVNO ──────────────────────────────────────────────────────
    local defaultPath = maxFilePath + (getFilenameFile maxFileName) + "_mesh.txt"
    local savePath = getSaveFileName \
        caption:"Sacuvaj ASCII mesh" \
        filename:defaultPath \
        types:"Text files (*.txt)|*.txt|All files (*.*)|*.*"

    if savePath != undefined then (
        if exportSceneToASCII savePath then
            messageBox ("Export zavrsen:\n" + savePath)
        else
            messageBox "Export nije uspeo. Pogledaj MAXScript Listener za detalje."
    )
)
