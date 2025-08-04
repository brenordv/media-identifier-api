import inspect

OUTPUT: str = ""

def extract_season_episode_from_filename(_input_filename: str) -> str:
    # Input: Takes in a filename string that is known to represent a TV show episode.
    # Function: Extracts and returns the season and episode number in the format: "season:X, episode:Y" (e.g., "season:1, episode:2").
    # Important:
    # - Only return the season and episode numbers, not titles, quality, or any other info.
    # - Detect SxxEyy, 1x02, or similar patterns.
    # - For double-episode files, return the first episode (e.g., S01E01E02 = episode 1).
    # - If you cannot reasonably extract both season and episode, return "unknown" (this must be your last resort).
    # - Output must match exactly: "season:X, episode:Y" (no leading zeros, no explanation).
    # Examples:
    # - "Breaking.Bad.S05E14.720p.HDTV.x264-IMMERSE.mkv" -> season:5, episode:14
    # - "Game.of.Thrones.S08E03.1080p.WEB.H264-MEMENTO.mkv" -> season:8, episode:3
    # - "Stranger.Things.S04E01.Chapter.One.720p.NF.WEB-DL.DDP5.1.x264-NTb.mkv" -> season:4, episode:1
    # - "Friends.2x11.480p.DVD.x264-SAiNTS.mkv" -> season:2, episode:11
    # - "The.Office.US.S07E17.720p.NF.WEB-DL.DDP5.1.x264-NTb.mkv" -> season:7, episode:17
    # - "The.Witcher.S01E01.720p.WEBRip.x264-GalaxyTV.mkv" -> season:1, episode:1
    # - "Lost.S01E01.Pilot.1080p.BluRay.x264-ROVERS.mkv" -> season:1, episode:1
    # - "Chernobyl.2019.S01E03.720p.WEB-DL.x264-MEMENTO.mkv" -> season:1, episode:3
    # - "The.Expanse.S03E08.720p.WEB-DL.x264-MEMENTO.mkv" -> season:3, episode:8
    # - "True.Detective.S02E01.720p.HDTV.x264-KILLERS.mkv" -> season:2, episode:1
    # - "ShowName_S06_E12_HDTV.mp4" -> season:6, episode:12
    # - "Rick.and.Morty.S05E01E02.720p.WEBRip.x264-ION10.mkv" -> season:5, episode:1
    # - "Seinfeld.821.720p.HDTV.x264-GROUP.mkv" -> season:8, episode:21
    # - "13.Reasons.Why.S02E01.mkv" -> season:2, episode:1
    # - "24.S01E01.avi" -> season:1, episode:1
    # - "CSI.204.avi" -> season:2, episode:4
    # - "ER.101.avi" -> season:1, episode:1
    # - "Battlestar.Galactica.2004.S01E01.33.720p.BluRay.x264.mkv" -> season:1, episode:1
    # - "Breaking.Bad.S05E14.720p.HDTV.x264-IMMERSE\CD1\bb-s05e14.r11" -> season:5, episode:14
    # - "shows/Game.of.Thrones.S08E03.1080p.WEB.H264-MEMENTO\DISC1\got-s08e03.mkv" -> season:8, episode:3
    # - "Stranger.Things.S04E01.Chapter.One.720p.NF.WEB-DL.DDP5.1.x264-NTb\CD2\st-s04e01.r10" -> season:4, episode:1
    # - "The.Office.US.S07E17.720p.NF.WEB-DL.DDP5.1.x264-NTb\PART1\office-s07e17.avi" -> season:7, episode:17
    # - "favs/Friends.2x11.480p.DVD.x264-SAiNTS\CD1\friends-2x11.rar" -> season:2, episode:11
    # - "Lost.S04E02.PT-BR.1080p.WEB-DL\CD2\lost-s04e02.mp4" -> season:4, episode:2
    # - "sci-fi/The.Expanse.S03E08.720p.WEB-DL.x264-MEMENTO\CD1\expanse-s03e08.r14" -> season:3, episode:8
    # - "Game of Thrones S08E03 1080p WEB H264-MEMENTO.mkv" ->  season:8, episode:3
    # - "Better Call Saul S03E05 1080p AMZN WEBRip DDP5.1 x264-NTb.zip" -> season:3, episode:5
    # - "Rick and Morty S05E01E02 720p WEBRip x264-ION10.rar" -> season:5, episode:1
    # - "The Mandalorian/S01E02 720p WEBRip x264-GalaxyTV.part1.rar" -> season:1, episode:2
    # - "Stranger Things/S04E01 Chapter One 720p NF WEB-DL DDP5.1 x264-NTb.r999" -> season:4, episode:1
    # - "The Office/US S07E17 720p NF WEB-DL DDP5.1 x264-NTb.r15" -> season:7, episode:17
    # - "Sherlock S02 E03 1080p BluRay x264-SHORTCUT.mkv" -> season:2, episode:3
    # - "True Detective S02E01 720p HDTV x264-KILLERS.zip" -> season:2, episode:1
    # - "README.txt" -> unknown
    return OUTPUT


if __name__ == '__main__':
    print(inspect.getsource(extract_season_episode_from_filename))
