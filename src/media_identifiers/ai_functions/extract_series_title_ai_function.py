import inspect

OUTPUT: str = ""


def extract_tv_show_title_from_filename(_input_filename: str) -> str:
    # Input: Takes in a filename string that is known to represent a TV show episode (not a movie, film or any other type of media.
    # Function: Extracts and returns only the title of the TV show, cleaned and as close as possible to the original show name, with spaces and proper capitalization.
    # Important:
    # - Ignore season/episode markers, year, quality, codecs, group tags, scene group name, file extension, and any extra descriptors.
    # - Return only the show title—no year, no S01E01, no group tags, no explanation, no context.
    # - Format the title with spaces and proper capitalization (e.g., "Game of Thrones").
    # - Remove dots, dashes, and underscores that separate title words.
    # - If you cannot reasonably extract a TV show title, as your last resort, return "unknown".
    # - The output must be a single line, with no extra spaces at the start or end.
    # Examples:
    # - "Breaking.Bad.S05E14.720p.HDTV.x264-IMMERSE.mkv" -> Breaking Bad
    # - "Game.of.Thrones.S08E03.1080p.WEB.H264-MEMENTO.mkv" -> Game of Thrones
    # - "Stranger.Things.S04E01.Chapter.One.720p.NF.WEB-DL.DDP5.1.x264-NTb.mkv" -> Stranger Things
    # - "Friends.2x11.480p.DVD.x264-SAiNTS.mkv" -> Friends
    # - "The.Office.US.S07E17.720p.NF.WEB-DL.DDP5.1.x264-NTb.mkv" -> The Office US
    # - "The.Witcher.S01E01.720p.WEBRip.x264-GalaxyTV.mkv" -> The Witcher
    # - "Better.Call.Saul.S03E05.1080p.AMZN.WEBRip.DDP5.1.x264-NTb.mkv" -> Better Call Saul
    # - "Lost.S01E01.Pilot.1080p.BluRay.x264-ROVERS.mkv" -> Lost
    # - "Chernobyl.2019.S01E03.720p.WEB-DL.x264-MEMENTO.mkv" -> Chernobyl
    # - "The.Expanse.S03E08.720p.WEB-DL.x264-MEMENTO.mkv" -> The Expanse
    # - "True.Detective.S02E01.720p.HDTV.x264-KILLERS.mkv" -> True Detective
    # - "The.Mandalorian.S01E02.720p.WEBRip.x264-GalaxyTV.mkv" -> The Mandalorian
    # - "ShowName_S06_E12_HDTV.mp4" -> Show Name
    # - "Rick.and.Morty.S05E01E02.720p.WEBRip.x264-ION10.mkv" -> Rick and Morty
    # - "Seinfeld.821.720p.HDTV.x264-GROUP.mkv" -> Seinfeld
    # - "Battlestar.Galactica.2004.S01E01.33.720p.BluRay.x264.mkv" -> Battlestar Galactica 2004
    # - "13.Reasons.Why.S02E01.mkv" -> 13 Reasons Why
    # - "24.S01E01.avi" -> 24
    # - "CSI.204.avi" -> CSI
    # - "ER.101.avi" -> ER
    # - "Room.104.2017.1080p.WEBRip.x264-STRiFE.mkv" -> Room 104
    # - "Breaking.Bad.S05E14.720p.HDTV.x264-IMMERSE\CD1\bb-s05e14.r11" -> Breaking Bad
    # - "shows/Game.of.Thrones.S08E03.1080p.WEB.H264-MEMENTO\DISC1\got-s08e03.mkv" -> Game of Thrones
    # - "Stranger.Things.S04E01.Chapter.One.720p.NF.WEB-DL.DDP5.1.x264-NTb\CD2\st-s04e01.r10" -> Stranger Things
    # - "The.Office.US.S07E17.720p.NF.WEB-DL.DDP5.1.x264-NTb\PART1\office-s07e17.avi" -> The Office
    # - "favs/Friends.2x11.480p.DVD.x264-SAiNTS\CD1\friends-2x11.rar" -> Friends
    # - "Lost.S04E02.PT-BR.1080p.WEB-DL\CD2\lost-s04e02.mp4" -> Lost
    # - "sci-fi/The.Expanse.S03E08.720p.WEB-DL.x264-MEMENTO\CD1\expanse-s03e08.r14" -> The Expanse
    # - "Game of Thrones S08E03 1080p WEB H264-MEMENTO.mkv" -> Game of Thrones
    # - "Better Call Saul S03E05 1080p AMZN WEBRip DDP5.1 x264-NTb.zip" -> Better Call Saul
    # - "Rick and Morty S05E01E02 720p WEBRip x264-ION10.rar" -> Rick and Morty
    # - "The Mandalorian/S01E02 720p WEBRip x264-GalaxyTV.part1.rar" -> The Mandalorian
    # - "Stranger Things/S04E01 Chapter One 720p NF WEB-DL DDP5.1 x264-NTb.r999" -> Stranger Things
    # - "The Office/US S07E17 720p NF WEB-DL DDP5.1 x264-NTb.r15" -> The Office US
    # - "Sherlock S02 E03 1080p BluRay x264-SHORTCUT.mkv" -> Sherlock
    # - "True Detective S02E01 720p HDTV x264-KILLERS.zip" -> True Detective
    # - "README.txt" -> unknown
    return OUTPUT


if __name__ == '__main__':
    print(inspect.getsource(extract_tv_show_title_from_filename))
