--------------------------------------------------------------------------------
-- export_ascii.ms
-- Konverzija 3ds Max scene u ASCII format iz zadatka:
--
--     <broj tacaka>
--     <broj trouglova>
--     x y z          (po jedan red za svaku tacku)
--     a b c          (po jedan red za svaki trougao, indeksi 0-based)
--
-- Poziva se iz core/converter.py, koji putanje prosledjuje kroz promenljive
-- okoline MAX_INPUT i MAX_OUTPUT. Bez njih radi interaktivno, sa dijalogom.
--
-- VAZNO: ceo posao je umotan u try/catch i greska se upisuje u <izlaz>.err.
-- Skripta se pokrece kao startup script (-U MAXScript); ako startup skripta
-- baci izuzetak, Max to prijavi kao pad instalacije i ponudi "Restore Factory
-- Settings", sto zbunjuje korisnika. Zato odavde ne sme da izadje izuzetak.
--
-- FORMAT BROJEVA: formattedPrint format:".6f" daje isti zapis kao profesorov
-- TORUS.txt ("102.921271 -0.000006 -65.231792"). Obican `format "%" v.x` NE
-- valja jer stampa 6 znacajnih cifara i prelazi u naucnu notaciju, pa bi
-- -0.000006 ispalo kao "-6e-06".
--
-- KOORDINATE: pisu se sirovo, tacno kako stoje u Max-u. Provereno merenjem:
-- 1.max exportovan ovom skriptom i uporedjen sa profesorovom elisa.txt (isti
-- model) -> 673/1042 tacaka se poklapa (64.6%) sa sirovim koordinatama, a
-- 0/1042 ako se radi Y-up zamena osa. Dakle nikakva konverzija se ne radi.
--------------------------------------------------------------------------------

fn writeError errPath msg = (
    -- Greska ide i u Listener i u fajl, da je Python strana moze procitati.
    format "GRESKA: %\n" msg
    if errPath != undefined and errPath != "" then (
        try (
            local ef = createFile errPath
            if ef != undefined then (
                format "%\n" msg to:ef
                close ef
            )
        ) catch ()
    )
)

fn collectMeshObjects = (
    local result = #()
    for o in geometry do (
        if (canConvertTo o TriMeshGeometry) then append result o
    )
    result
)

fn exportSceneToASCII outPath = (
    local objs = collectMeshObjects()
    if objs.count == 0 then
        throw "u sceni nema geometrije koja se moze konvertovati u mesh"

    -- snapshotAsMesh primenjuje transformaciju objekta, pa su koordinate vec
    -- u svetskom prostoru.
    local meshes = #()
    local totalV = 0
    local totalF = 0
    for o in objs do (
        local m = snapshotAsMesh o
        append meshes m
        totalV += m.numverts
        totalF += m.numfaces
    )

    -- createFile, ne openFile — openFile je za citanje postojeceg fajla.
    local f = createFile outPath
    if f == undefined then
        throw ("ne mogu da otvorim izlazni fajl: " + outPath)

    format "%\n" totalV to:f
    format "%\n" totalF to:f

    -- 1) sve tacke, redom po objektima
    for m in meshes do (
        for i = 1 to m.numverts do (
            local v = getVert m i
            local sx = formattedPrint v.x format:".6f"
            local sy = formattedPrint v.y format:".6f"
            local sz = formattedPrint v.z format:".6f"
            format "% % %\n" sx sy sz to:f
        )
    )

    -- 2) svi trouglovi; MAXScript indeksira od 1, format iz zadatka od 0, a
    --    svaki sledeci objekat se pomera za broj vec ispisanih tacaka.
    local offset = 0
    for m in meshes do (
        for i = 1 to m.numfaces do (
            local fc = getFace m i
            local ia = (fc.x as integer) - 1 + offset
            local ib = (fc.y as integer) - 1 + offset
            local ic = (fc.z as integer) - 1 + offset
            format "% % %\n" ia ib ic to:f
        )
        offset += m.numverts
    )

    close f
    try (for m in meshes do delete m) catch ()

    format "OK: % objekata, % tacaka, % trouglova -> %\n" objs.count totalV totalF outPath
    true
)

--------------------------------------------------------------------------------
-- Ulazna tacka
--------------------------------------------------------------------------------

(
    local inPath = undefined
    local outPath = undefined
    local errPath = undefined

    try (
        inPath  = systemTools.getEnvVariable "MAX_INPUT"
        outPath = systemTools.getEnvVariable "MAX_OUTPUT"
    ) catch ()

    if outPath != undefined and outPath != "" then errPath = outPath + ".err"

    try (
        if outPath != undefined and outPath != "" then (
            -- Automatski rezim: putanje su stigle iz aplikacije.
            if inPath != undefined and inPath != "" then (
                if not (doesFileExist inPath) then
                    throw ("ulazni .max fajl ne postoji: " + inPath)
                if not (loadMaxFile inPath quiet:true) then
                    throw ("loadMaxFile nije uspeo: " + inPath)
            )
            exportSceneToASCII outPath
            quitMax #noPrompt
        )
        else (
            -- Interaktivni rezim: exportuj trenutnu scenu, pitaj gde.
            local defaultPath = maxFilePath + (getFilenameFile maxFileName) + "_mesh.txt"
            local savePath = getSaveFileName caption:"Sacuvaj ASCII mesh" filename:defaultPath types:"Text files (*.txt)|*.txt|All files (*.*)|*.*"
            if savePath != undefined then (
                exportSceneToASCII savePath
                messageBox ("Export zavrsen:\n" + savePath)
            )
        )
    )
    catch (
        -- Nijedan izuzetak ne sme da izadje iz startup skripte.
        writeError errPath (getCurrentException())
        if outPath != undefined and outPath != "" then quitMax #noPrompt
    )
)
