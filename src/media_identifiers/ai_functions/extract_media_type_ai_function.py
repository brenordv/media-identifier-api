import inspect

OUTPUT: str = ""

def extract_media_type_from_filename(_input_filename: str) -> str:
    # Input: Takes in the filename the user wants to be analyzed.
    # Function: Analyzes the input filename and returns if it is a movie or tv-show.
    # Important:
    # - Work to the best of your knowledge and use filename conventions to make an informed decision.
    # - Only if you cannot reasonably determine whether the filename represents a movie or a TV show episode, return "unknown".
    # - "unknown" must be your last resort—try to classify as "movie" or "tv" whenever possible.
    # - The output must be exactly one of: "movie", "tv", or "unknown". No explanation or context. No other value.
    # - Output must be a single token: "movie", "tv", or "unknown". No leading or trailing spaces or newlines.
    # - Ignore the file extension and letter case when analyzing the filename.
    # Output:
    # - If the filename string contains the name of a Movie, return "movie";
    # - If the filename string contains an indication for a TV Show episode, return "tv".
    # - If you cannot reasonably classify, return "unknown" as a last resort.
    # Examples:
    # - "The.Matrix.1999.1080p.BluRay.x264.DTS-FGT.mkv" -> movie
    # - "Breaking.Bad.S05E14.720p.HDTV.x264-IMMERSE.mkv" -> tv
    # - "Inception.2010.720p.BluRay.x264.YIFY.mp4" -> movie
    # - "Game.of.Thrones.S08E03.1080p.WEB.H264-MEMENTO.mkv" -> tv
    # - "Parasite.2019.KOREAN.1080p.BluRay.x264.DTS-FGT.mkv" -> movie
    # - "Stranger.Things.S04E01.Chapter.One.720p.NF.WEB-DL.DDP5.1.x264-NTb.mkv" -> tv
    # - "1917.2019.2160p.UHD.BluRay.X265-IAMABLE.mkv" -> movie
    # - "Friends.2x11.480p.DVD.x264-SAiNTS.mkv" -> tv
    # - "Spider-Man.Into.the.Spider-Verse.2018.1080p.BluRay.x264.YIFY.mp4" -> movie
    # - "The.Office.US.S07E17.720p.NF.WEB-DL.DDP5.1.x264-NTb.mkv" -> tv
    # - "Joker.2019.720p.BluRay.x264.YIFY.mp4" -> movie
    # - "The.Witcher.S01E01.720p.WEBRip.x264-GalaxyTV.mkv" -> tv
    # - "Gladiator.2000.1080p.BluRay.x264.YIFY.mp4" -> movie
    # - "Better.Call.Saul.S03E05.1080p.AMZN.WEBRip.DDP5.1.x264-NTb.mkv" -> tv
    # - "Mad.Max.Fury.Road.2015.720p.BluRay.x264.YIFY.mp4" -> movie
    # - "Lost.S01E01.Pilot.1080p.BluRay.x264-ROVERS.mkv" -> tv
    # - "Interstellar.2014.1080p.BluRay.x264.YIFY.mp4" -> movie
    # - "Chernobyl.2019.S01E03.720p.WEB-DL.x264-MEMENTO.mkv" -> tv
    # - "Jaws.1975.720p.BluRay.x264.YIFY.mp4" -> movie
    # - "The.Expanse.S03E08.720p.WEB-DL.x264-MEMENTO.mkv" -> tv
    # - "La.La.Land.2016.1080p.BluRay.x264.YIFY.mp4" -> movie
    # - "True.Detective.S02E01.720p.HDTV.x264-KILLERS.mkv" -> tv
    # - "Forrest.Gump.1994.720p.BluRay.x264.YIFY.mp4" -> movie
    # - "The.Mandalorian.S01E02.720p.WEBRip.x264-GalaxyTV.mkv" -> tv
    # - "Show.Name.2022.2x07.720p.WEB-DL.mkv" -> tv
    # - "Movie.2020.1080p.WEB-DL.H264-RARBG.avi" -> movie
    # - "The.Wire.03x11.avi" -> tv
    # - "Movie.Title.2019.m2ts" -> movie
    # - "Sherlock.S02.E03.1080p.BluRay.x264-SHORTCUT.mkv" -> tv
    # - "Avatar.2.2022.2160p.UHD.BluRay.x265.mkv" -> movie
    # - "Show.Name.S03E05-E06.720p.HDTV.x264-GROUP.mkv" -> tv
    # - "Dune.Part.One.2021.1080p.BluRay.x264-GROUP.mkv" -> movie
    # - "Rick.and.Morty.S05E01E02.720p.WEBRip.x264-ION10.mkv" -> tv
    # - "Edge.of.Tomorrow.2014.720p.BluRay.x264.YIFY.mkv" -> movie
    # - "The.Walking.Dead.1001.1080p.WEB.H264-STRiFE.mkv" -> tv
    # - "Show.Name.-.S04E10.-.The.Finale.mkv" -> tv
    # - "King.Kong.1933.REMASTERED.720p.BluRay.x264-GROUP.mkv" -> movie
    # - "ShowName_S06_E12_HDTV.mp4" -> tv
    # - "Blade.Runner.2049.2017.1080p.BluRay.x264-GROUP.mkv" -> movie
    # - "Movie.2001.Space.Odyssey.1968.720p.BluRay.x264.YIFY.mp4" -> movie
    # - "Seinfeld.821.720p.HDTV.x264-GROUP.mkv" -> tv
    # - "Alien3.1992.720p.BluRay.x264.YIFY.mp4" -> movie
    # - "Battlestar.Galactica.2004.S01E01.33.720p.BluRay.x264.mkv" -> tv
    # - "Up.2009.1080p.BluRay.x264.YIFY.mp4" -> movie
    # - "The.Matrix.1999.1080p.BluRay.x264.DTS-FGT.rar" -> movie
    # - "Breaking.Bad.S02E10.720p.HDTV.x264-IMMERSE.r00" -> tv
    # - "Inception.2010.1080p.BluRay.x264.YIFY.7z" -> movie
    # - "The.Office.US.S01E05.720p.WEB-DL.x264.part1.rar" -> tv
    # - "Joker.2019.BluRay.x264.YIFY.zip" -> movie
    # - "Stranger.Things.S03E01.001" -> tv
    # - "True.Detective.S02E03.720p.HDTV.x264-KILLERS.r001" -> tv
    # - "Avatar.2009.DISC2.ISO" -> movie
    # - "Lost.S04E02.PT-BR.1080p.WEB-DL.mkv" -> tv
    # - "Better.Call.Saul.S01E07.720p.WEB-DL.x264-GROUP.part02.rar" -> tv
    # - "Forrest.Gump.1994.DISC1.1080p.BluRay.iso" -> movie
    # - "Se7en.1995.avi" -> movie
    # - "24.S01E01.avi" -> tv
    # - "13.Reasons.Why.S02E01.mkv" -> tv
    # - "2012.2009.BluRay.avi" -> movie
    # - "John.Wick.Chapter.3.Parabellum.2019.720p.BluRay.mkv" -> movie
    # - "ER.101.avi" -> tv
    # - "The.Witcher.S01E01.mkv" -> tv
    # - "Fight.Club.1999.mkv" -> movie
    # - "10.Things.I.Hate.About.You.1999.mkv" -> movie
    # - "CSI.204.avi" -> tv
    # - "District.9.2009.BluRay.x264.YIFY.mp4" -> movie
    # - "Room.104.2017.1080p.WEBRip.x264-STRiFE.mkv" -> tv
    # - "The.Number.23.2007.DVDRip.x264.avi" -> movie
    # - "Friday.the.13th.2009.BluRay.avi" -> movie
    # - "Stephen King\The.Lawnmower.Man.1992.DVDRiP.XviD.iNTERNAL-JUSTRiP\CD1\jrp-tlma.r05" -> movie
    # - "Pulp.Fiction.1994.DVDRip.XviD.AC3\DISC2\pulpfict-ac3.r03" -> movie
    # - "Gladiator.2000.720p.BluRay.x264-YIFY\CD2\glad-yify.mkv" -> movie
    # - "Inception.2010.1080p.BluRay.x264.YIFY\Part2\incept-yify.avi" -> movie
    # - "classics/Jaws.1975.720p.BluRay.x264.YIFY\CD1\jaws1975-yify.mp4" -> movie
    # - "Blade.Runner.2049.2017.2160p.UHD.BluRay.x265\CD1\blade2049-gp.avi" -> movie
    # - "sci-fi/Avatar.2.2022.2160p.UHD.BluRay.x265\CD2\avat2-uhd.r05" -> movie
    # - "Mad.Max.Fury.Road.2015.720p.BluRay.x264-YIFY\CD1\madmax-yify.avi" -> movie
    # - "best/King.Kong.1933.REMASTERED.720p.BluRay.x264\CD2\kong1933-remast.mp4" -> movie
    # - "Breaking.Bad.S05E14.720p.HDTV.x264-IMMERSE\CD1\bb-s05e14.r11" -> tv
    # - "shows/Game.of.Thrones.S08E03.1080p.WEB.H264-MEMENTO\DISC1\got-s08e03.mkv" -> tv
    # - "Stranger.Things.S04E01.Chapter.One.720p.NF.WEB-DL.DDP5.1.x264-NTb\CD2\st-s04e01.r10" -> tv
    # - "The.Office.US.S07E17.720p.NF.WEB-DL.DDP5.1.x264-NTb\PART1\office-s07e17.avi" -> tv
    # - "favs/Friends.2x11.480p.DVD.x264-SAiNTS\CD1\friends-2x11.r06" -> tv
    # - "Lost.S04E02.PT-BR.1080p.WEB-DL\CD2\lost-s04e02.mp4" -> tv
    # - "sci-fi/The.Expanse.S03E08.720p.WEB-DL.x264-MEMENTO\CD1\expanse-s03e08.r14" -> tv
    # - "The Shawshank Redemption 1994 1080p BluRay x264 YIFY.mp4" -> movie
    # - "Game of Thrones S08E03 1080p WEB H264-MEMENTO.mkv" -> tv
    # - "Better Call Saul S03E05 1080p AMZN WEBRip DDP5.1 x264-NTb.mkv" -> tv
    # - "Forrest Gump 1994 720p BluRay x264 YIFY.mp4" -> movie
    # - "Rick and Morty S05E01E02 720p WEBRip x264-ION10.mkv" -> tv
    # - "The Mandalorian/S01E02 720p WEBRip x264-GalaxyTV.mkv" -> tv
    # - "Mad Max Fury Road 2015 720p BluRay x264 YIFY.mp4" -> movie
    # - "Stranger Things/S04E01 Chapter One 720p NF WEB-DL DDP5.1 x264-NTb.mkv" -> tv
    # - "10 Things I Hate About You 1999.mkv" -> movie
    # - "Movies Super Hero/Spider-Man Into the Spider-Verse 2018 1080p BluRay x264 YIFY.mp4" -> movie
    # - "The Office/US S07E17 720p NF WEB-DL DDP5.1 x264-NTb.mkv" -> tv
    # - "Sherlock S02 E03 1080p BluRay x264-SHORTCUT.mkv" -> tv
    # - "King Kong 1933 REMASTERED 720p BluRay x264-GROUP.mkv" -> movie
    # - "Edge of Tomorrow 2014 720p BluRay x264 YIFY.mkv" -> movie
    # - "True Detective S02E01 720p HDTV x264-KILLERS.mkv" -> tv
    # - "Show Name 2022 2x07 720p WEB-DL.mkv" -> tv
    # - "Blade Runner 2049 2017 1080p BluRay x264-GROUP.mkv" -> movie
    # - "La La Land 2016 1080p BluRay x264 YIFY.mp4" -> movie
    # - "John Wick Chapter 3 Parabellum 2019 720p BluRay.mkv" -> movie
    # - "Friday.The.13th.The.Final.Chapter.1984.REMASTERED.1080P.BLURAY.X264-WATCHABLE.mkv" -> movie
    # - "Friday.The.13th.S03E20.The.Channel.Pit.REMASTERED.1080P.BLURAY.X264-WATCHABLE.mkv" -> tv
    # - "readme.md" -> unknown
    return OUTPUT


if __name__ == '__main__':
    print(inspect.getsource(extract_media_type_from_filename))
