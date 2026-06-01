This project is to streamline the transfer of zeo records to Oscar
currently the output of ZeoDataDecoder has a couple of issues, the time is offset by 5 hours for the start of night, end of night, and rise time, so it says 3:14 but should be 8:18, additionally, times that fall before midnight (usually just start of night) are not in 24 hour notation and so should be advanced by 12 hours.
java -jar ZeoDataDecoder.jar ZEOSLEEP.DAT > zeosleep.csv
the goal of this project is to, when run, automatically pull the data from the .dat file, decode it, and allow me to select which days will be output into a csv file that I will upload to Oscar. the gui should show the original time and the corrected time, with an option for me to override the corrected time, and then allow me to generate an output file.
utilize python for this project

zeosleep_corrected.csv is an example corrected file I have manually made
ZEOSLEEP.DAT is an example input file
zeosleep.csv is the current output	
ZeoDataDecoder.jar is a decoder provided already
