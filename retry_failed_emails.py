import os, sys, time, logging, re
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "app"))

from database import get_all_profiles, initialize_firebase
from send_promo_emails import send_update_promo_email

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s  %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
logger = logging.getLogger("promo_retry")

raw_log_text = """
2026-09-16 16:21:44,338 - ERROR - ❌ Failed to send email to otienoibrahim481@gmail.com: Connection unexpectedly closed: [WinError 10054] An existing connection was forcibly closed by the remote host
2026-09-16 16:21:44,342 - ERROR - [147/243] FAILED -> Ibrahim <otienoibrahim481@gmail.com>
2026-09-16 16:21:45,959 - ERROR - ❌ Failed to send email to bonfacenyongesaomondi@gmail.com: [WinError 10054] An existing connection was forcibly closed by the remote host
2026-09-16 16:21:45,959 - ERROR - [148/243] FAILED -> bonfacenyongesaomondi@gmail.com <bonfacenyongesaomondi@gmail.com>
2026-09-16 16:21:47,800 - ERROR - ❌ Failed to send email to nashonnjoroge9@gmail.com: [WinError 10054] An existing connection was forcibly closed by the remote host
2026-09-16 16:21:47,801 - ERROR - [149/243] FAILED -> Nashon Njoroge Mwita <nashonnjoroge9@gmail.com>
2026-09-16 16:21:49,855 - ERROR - ❌ Failed to send email to kebeethomas@gmail.com: [WinError 10054] An existing connection was forcibly closed by the remote host
2026-09-16 16:21:49,855 - ERROR - [150/243] FAILED -> Thomas Kebee <kebeethomas@gmail.com>
2026-09-16 16:21:51,761 - ERROR - ❌ Failed to send email to mokuadouglas44@gmail.com: [WinError 10054] An existing connection was forcibly closed by the remote host
2026-09-16 16:21:51,763 - ERROR - [151/243] FAILED -> Douglas <mokuadouglas44@gmail.com>
2026-09-16 16:21:54,036 - ERROR - ❌ Failed to send email to odoyogodfrey1@gmail.com: [WinError 10054] An existing connection was forcibly closed by the remote host
2026-09-16 16:21:54,037 - ERROR - [152/243] FAILED -> Junior <odoyogodfrey1@gmail.com>
2026-09-16 16:21:56,678 - ERROR - ❌ Failed to send email to owuorfabregas001@gmail.com: [WinError 10054] An existing connection was forcibly closed by the remote host
2026-09-16 16:21:56,678 - ERROR - [153/243] FAILED -> Fabregas Odhiambo <owuorfabregas001@gmail.com>
2026-09-16 16:21:58,424 - ERROR - ❌ Failed to send email to kadimahjosseh668@gmail.com: [WinError 10054] An existing connection was forcibly closed by the remote host
2026-09-16 16:21:58,425 - ERROR - [154/243] FAILED -> Prince <kadimahjosseh668@gmail.com>
2026-09-16 16:22:00,557 - ERROR - ❌ Failed to send email to bgichana2000@gmail.com: [WinError 10054] An existing connection was forcibly closed by the remote host
2026-09-16 16:22:00,558 - ERROR - [155/243] FAILED -> Prince Ben <bgichana2000@gmail.com>
2026-09-16 16:22:02,512 - ERROR - ❌ Failed to send email to emmanuelsimiyu2004@gmail.com: [WinError 10054] An existing connection was forcibly closed by the remote host
2026-09-16 16:22:02,513 - ERROR - [156/243] FAILED -> emmanuel simiyu <emmanuelsimiyu2004@gmail.com>
2026-09-16 16:22:04,149 - ERROR - ❌ Failed to send email to stephenaruru9@gmail.com: [WinError 10054] An existing connection was forcibly closed by the remote host
2026-09-16 16:22:04,150 - ERROR - [157/243] FAILED -> Sammy bichage <stephenaruru9@gmail.com>
2026-09-16 16:22:05,815 - ERROR - ❌ Failed to send email to edersonmildon@gmail.com: [WinError 10054] An existing connection was forcibly closed by the remote host
2026-09-16 16:22:05,816 - ERROR - [158/243] FAILED -> Danson Williams <edersonmildon@gmail.com>
2026-09-16 16:22:07,584 - ERROR - ❌ Failed to send email to mogekadenis092@gmail.com: [WinError 10054] An existing connection was forcibly closed by the remote host
2026-09-16 16:22:07,585 - ERROR - [159/243] FAILED -> Mogeka Denis <mogekadenis092@gmail.com>
2026-09-16 16:22:09,237 - ERROR - ❌ Failed to send email to levihdefinger6@gmail.com: [WinError 10054] An existing connection was forcibly closed by the remote host
2026-09-16 16:22:09,238 - ERROR - [160/243] FAILED -> Young Toothless <levihdefinger6@gmail.com>
2026-09-16 16:22:11,269 - ERROR - ❌ Failed to send email to manlincolin@gmail.com: [WinError 10054] An existing connection was forcibly closed by the remote host
2026-09-16 16:22:11,270 - ERROR - [161/243] FAILED -> Lincoln Mandila Barasa <manlincolin@gmail.com>
2026-09-16 16:22:12,947 - ERROR - ❌ Failed to send email to odoyogodfrey1@gmail.com: [WinError 10054] An existing connection was forcibly closed by the remote host
2026-09-16 16:22:12,947 - ERROR - [162/243] FAILED -> Junior <odoyogodfrey1@gmail.com>
2026-09-16 16:22:14,724 - ERROR - ❌ Failed to send email to fidelochola9@gmail.com: [WinError 10054] An existing connection was forcibly closed by the remote host
2026-09-16 16:22:14,724 - ERROR - [163/243] FAILED -> Ken ten <fidelochola9@gmail.com>
2026-09-16 16:22:16,850 - ERROR - ❌ Failed to send email to diorseb3560@gmail.com: [WinError 10054] An existing connection was forcibly closed by the remote host
2026-09-16 16:22:16,850 - ERROR - [164/243] FAILED -> Memba Sebastin <diorseb3560@gmail.com>
2026-09-16 16:22:18,798 - ERROR - ❌ Failed to send email to obamaonyi@gmail.com: [WinError 10054] An existing connection was forcibly closed by the remote host
2026-09-16 16:22:18,798 - ERROR - [165/243] FAILED -> caniel obby <obamaonyi@gmail.com>
2026-09-16 16:22:21,060 - ERROR - ❌ Failed to send email to chebusirideiney@gmail.com: [WinError 10054] An existing connection was forcibly closed by the remote host
2026-09-16 16:22:21,060 - ERROR - [166/243] FAILED -> Dewey <chebusirideiney@gmail.com>
2026-09-16 16:22:23,501 - ERROR - ❌ Failed to send email to onyangoleenus@gmail.com: [WinError 10054] An existing connection was forcibly closed by the remote host
2026-09-16 16:22:23,501 - ERROR - [167/243] FAILED -> Leenus Onyango <onyangoleenus@gmail.com>
2026-09-16 16:22:25,258 - ERROR - ❌ Failed to send email to mukulunichael73@gmail.com: [WinError 10054] An existing connection was forcibly closed by the remote host
2026-09-16 16:22:25,258 - ERROR - [168/243] FAILED -> Michael <mukulunichael73@gmail.com>
2026-09-16 16:22:27,134 - ERROR - ❌ Failed to send email to thevillageelder8@gmail.com: [WinError 10054] An existing connection was forcibly closed by the remote host
2026-09-16 16:22:27,135 - ERROR - [169/243] FAILED -> Peter Malaba Frederick <thevillageelder8@gmail.com>
2026-09-16 16:22:28,953 - ERROR - ❌ Failed to send email to bonfacenyongesaomondi@gmail.com: [WinError 10054] An existing connection was forcibly closed by the remote host
2026-09-16 16:22:28,953 - ERROR - [170/243] FAILED -> bonfacenyongesaomondi@gmail.com <bonfacenyongesaomondi@gmail.com>
2026-09-16 16:22:31,155 - ERROR - ❌ Failed to send email to emmanuelsimiyu2004@gmail.com: [WinError 10054] An existing connection was forcibly closed by the remote host
2026-09-16 16:22:31,155 - ERROR - [171/243] FAILED -> emmanuel simiyu <emmanuelsimiyu2004@gmail.com>
2026-09-16 16:22:33,274 - ERROR - ❌ Failed to send email to izzodegi@gmail.com: [WinError 10054] An existing connection was forcibly closed by the remote host
2026-09-16 16:22:33,275 - ERROR - [172/243] FAILED -> Owen <izzodegi@gmail.com>
2026-09-16 16:22:35,249 - ERROR - ❌ Failed to send email to mu.te.thiaa254@gmail.com: [WinError 10054] An existing connection was forcibly closed by the remote host
2026-09-16 16:22:35,250 - ERROR - [173/243] FAILED -> Kenneth Mutethia <mu.te.thiaa254@gmail.com>
2026-09-16 16:22:37,113 - ERROR - ❌ Failed to send email to makundadennis66@gmail.com: [WinError 10054] An existing connection was forcibly closed by the remote host
2026-09-16 16:22:37,113 - ERROR - [174/243] FAILED -> Radeen Mohammad <makundadennis66@gmail.com>
2026-09-16 16:22:39,171 - ERROR - ❌ Failed to send email to collinsratty0@gmail.com: [WinError 10054] An existing connection was forcibly closed by the remote host
2026-09-16 16:22:39,171 - ERROR - [175/243] FAILED -> collins ratty <collinsratty0@gmail.com>
2026-09-16 16:22:40,953 - ERROR - ❌ Failed to send email to kiseraclintone@gmail.com: [WinError 10054] An existing connection was forcibly closed by the remote host
2026-09-16 16:22:40,954 - ERROR - [176/243] FAILED -> Kisera Clintone <kiseraclintone@gmail.com>
2026-09-16 16:22:42,909 - ERROR - ❌ Failed to send email to mashaman220@gmail.com: [WinError 10054] An existing connection was forcibly closed by the remote host
2026-09-16 16:22:42,911 - ERROR - [177/243] FAILED -> mashaman <mashaman220@gmail.com>
2026-09-16 16:22:44,999 - ERROR - ❌ Failed to send email to fabianmairima36@gmail.com: [WinError 10054] An existing connection was forcibly closed by the remote host
2026-09-16 16:22:45,010 - ERROR - [178/243] FAILED -> Meech <fabianmairima36@gmail.com>
2026-09-16 16:22:46,976 - ERROR - ❌ Failed to send email to mcipher819@gmail.com: [WinError 10054] An existing connection was forcibly closed by the remote host
2026-09-16 16:22:46,978 - ERROR - [179/243] FAILED -> Cipher <mcipher819@gmail.com>
2026-09-16 16:22:48,869 - ERROR - ❌ Failed to send email to jmomusikoyo343@gmail.com: [WinError 10054] An existing connection was forcibly closed by the remote host
2026-09-16 16:22:48,869 - ERROR - [180/243] FAILED -> Joseph Mwanza <jmomusikoyo343@gmail.com>
2026-09-16 16:22:50,513 - ERROR - ❌ Failed to send email to kiprooemmanuel87@gmail.com: [WinError 10054] An existing connection was forcibly closed by the remote host
2026-09-16 16:22:50,514 - ERROR - [181/243] FAILED -> Emmanuel <kiprooemmanuel87@gmail.com>
2026-09-16 16:22:52,300 - ERROR - ❌ Failed to send email to simonfad126@gmail.com: [WinError 10054] An existing connection was forcibly closed by the remote host
2026-09-16 16:22:52,301 - ERROR - [182/243] FAILED -> Simon haka <simonfad126@gmail.com>
2026-09-16 16:22:54,829 - ERROR - ❌ Failed to send email to sheilacherotich@gmail.com: [WinError 10054] An existing connection was forcibly closed by the remote host
2026-09-16 16:22:54,830 - ERROR - [183/243] FAILED -> Sheila cherotich <sheilacherotich@gmail.com>
2026-09-16 16:22:56,591 - ERROR - ❌ Failed to send email to jmomusikoyo343@gmail.com: [WinError 10054] An existing connection was forcibly closed by the remote host
2026-09-16 16:22:56,592 - ERROR - [184/243] FAILED -> Joseph Mwanza <jmomusikoyo343@gmail.com>
2026-09-16 16:22:58,282 - ERROR - ❌ Failed to send email to ashiundustanley145@gmail.com: [WinError 10054] An existing connection was forcibly closed by the remote host
2026-09-16 16:22:58,283 - ERROR - [185/243] FAILED -> Stanley ashiundu <ashiundustanley145@gmail.com>
2026-09-16 16:22:59,989 - ERROR - ❌ Failed to send email to kadimahjosseh668@gmail.com: [WinError 10054] An existing connection was forcibly closed by the remote host
2026-09-16 16:22:59,990 - ERROR - [186/243] FAILED -> Prince <kadimahjosseh668@gmail.com>
2026-09-16 16:23:02,030 - ERROR - ❌ Failed to send email to wanyamad800@gmail.com: [WinError 10054] An existing connection was forcibly closed by the remote host
2026-09-16 16:23:02,032 - ERROR - [187/243] FAILED -> amos <wanyamad800@gmail.com>
2026-09-16 16:23:03,840 - ERROR - ❌ Failed to send email to glenwalucho688@gmail.com: [WinError 10054] An existing connection was forcibly closed by the remote host
2026-09-16 16:23:03,841 - ERROR - [188/243] FAILED -> Glen <glenwalucho688@gmail.com>
2026-09-16 16:23:05,761 - ERROR - ❌ Failed to send email to xxcityent@gmail.com: [WinError 10054] An existing connection was forcibly closed by the remote host
2026-09-16 16:23:05,762 - ERROR - [189/243] FAILED -> City <xxcityent@gmail.com>
2026-09-16 16:23:07,393 - ERROR - ❌ Failed to send email to otienowendyjoy@gmail.com: [WinError 10054] An existing connection was forcibly closed by the remote host
2026-09-16 16:23:07,394 - ERROR - [190/243] FAILED -> Wendy Joy <otienowendyjoy@gmail.com>
2026-09-16 16:23:09,080 - ERROR - ❌ Failed to send email to bururioisaac@gmail.com: [WinError 10054] An existing connection was forcibly closed by the remote host
2026-09-16 16:23:09,081 - ERROR - [191/243] FAILED -> Bururio Isaac's <bururioisaac@gmail.com>
2026-09-16 16:23:10,859 - ERROR - ❌ Failed to send email to nyagambistephen@gmail.com: [WinError 10054] An existing connection was forcibly closed by the remote host
2026-09-16 16:23:10,860 - ERROR - [192/243] FAILED -> Stephen <nyagambistephen@gmail.com>
2026-09-16 16:23:12,682 - ERROR - ❌ Failed to send email to charlesmbisi09@gmail.com: [WinError 10054] An existing connection was forcibly closed by the remote host
2026-09-16 16:23:12,683 - ERROR - [193/243] FAILED -> Buzz <charlesmbisi09@gmail.com>
2026-09-16 16:23:14,500 - ERROR - ❌ Failed to send email to odindofirst85@gmail.com: [WinError 10054] An existing connection was forcibly closed by the remote host
2026-09-16 16:23:14,501 - ERROR - [194/243] FAILED -> Geoffrey Omondi Obar <odindofirst85@gmail.com>
2026-09-16 16:23:16,317 - ERROR - ❌ Failed to send email to petersonragirakenyanya@gmail.com: [WinError 10054] An existing connection was forcibly closed by the remote host
2026-09-16 16:23:16,318 - ERROR - [195/243] FAILED -> Ragih Peterson <petersonragirakenyanya@gmail.com>
2026-09-16 16:23:17,989 - ERROR - ❌ Failed to send email to frankmunge679@gmail.com: [WinError 10054] An existing connection was forcibly closed by the remote host
2026-09-16 16:23:17,990 - ERROR - [196/243] FAILED -> Franklin Munge <frankmunge679@gmail.com>
2026-09-16 16:23:20,441 - ERROR - ❌ Failed to send email to oderawayne7@gmail.com: [WinError 10054] An existing connection was forcibly closed by the remote host
2026-09-16 16:23:20,443 - ERROR - [197/243] FAILED -> Wayne <oderawayne7@gmail.com>
2026-09-16 16:23:23,110 - ERROR - ❌ Failed to send email to makundadennis66@gmail.com: [WinError 10054] An existing connection was forcibly closed by the remote host
2026-09-16 16:23:23,111 - ERROR - [198/243] FAILED -> Dennis <makundadennis66@gmail.com>
2026-09-16 16:23:25,590 - ERROR - ❌ Failed to send email to ardamirambe15@gmail.com: [WinError 10054] An existing connection was forcibly closed by the remote host
2026-09-16 16:23:25,591 - ERROR - [199/243] FAILED -> Arda <ardamirambe15@gmail.com>
2026-09-16 16:23:27,446 - ERROR - ❌ Failed to send email to smithayub22@gmail.com: [WinError 10054] An existing connection was forcibly closed by the remote host
2026-09-16 16:23:27,447 - ERROR - [200/243] FAILED -> smith <smithayub22@gmail.com>
2026-09-16 16:23:29,134 - ERROR - ❌ Failed to send email to sildamba20@gmail.com: [WinError 10054] An existing connection was forcibly closed by the remote host
2026-09-16 16:23:29,135 - ERROR - [201/243] FAILED -> SILVESTER OGWENO MANG'ONG'O <sildamba20@gmail.com>
2026-09-16 16:23:31,683 - ERROR - ❌ Failed to send email to alphoncelamin@gmail.com: [WinError 10054] An existing connection was forcibly closed by the remote host
2026-09-16 16:23:31,684 - ERROR - [202/243] FAILED -> Alphonce kilui <alphoncelamin@gmail.com>
2026-09-16 16:23:33,545 - ERROR - ❌ Failed to send email to melcky695@gmail.com: [WinError 10054] An existing connection was forcibly closed by the remote host
2026-09-16 16:23:33,546 - ERROR - [203/243] FAILED -> Melchii zeddie <melcky695@gmail.com>
2026-09-16 16:23:35,165 - ERROR - ❌ Failed to send email to ianatete3@gmail.com: [WinError 10054] An existing connection was forcibly closed by the remote host
2026-09-16 16:23:35,166 - ERROR - [204/243] FAILED -> Ian <ianatete3@gmail.com>
2026-09-16 16:23:36,880 - ERROR - ❌ Failed to send email to alexbaraka78@gmail.com: [WinError 10054] An existing connection was forcibly closed by the remote host
2026-09-16 16:23:36,880 - ERROR - [205/243] FAILED -> Baraka <alexbaraka78@gmail.com>
2026-09-16 16:23:38,707 - ERROR - ❌ Failed to send email to glenwalucho688@gmail.com: [WinError 10054] An existing connection was forcibly closed by the remote host
2026-09-16 16:23:38,708 - ERROR - [206/243] FAILED -> Glen <glenwalucho688@gmail.com>
2026-09-16 16:23:40,350 - ERROR - ❌ Failed to send email to kelvinwainaina735@gmail.com: [WinError 10054] An existing connection was forcibly closed by the remote host
2026-09-16 16:23:40,351 - ERROR - [207/243] FAILED -> Kelvin Wainaina <kelvinwainaina735@gmail.com>
2026-09-16 16:23:42,008 - ERROR - ❌ Failed to send email to atrixmohivor@gmail.com: [WinError 10054] An existing connection was forcibly closed by the remote host
2026-09-16 16:23:42,009 - ERROR - [208/243] FAILED -> Atrix <atrixmohivor@gmail.com>
2026-09-16 16:23:43,673 - ERROR - ❌ Failed to send email to piusmtuweta42@gmail.com: [WinError 10054] An existing connection was forcibly closed by the remote host
2026-09-16 16:23:43,674 - ERROR - [209/243] FAILED -> Pius <piusmtuweta42@gmail.com>
2026-09-16 16:23:45,313 - ERROR - ❌ Failed to send email to khanarwa429@gmail.com: [WinError 10054] An existing connection was forcibly closed by the remote host
2026-09-16 16:23:45,313 - ERROR - [210/243] FAILED -> Arwa <khanarwa429@gmail.com>
2026-09-16 16:23:47,058 - ERROR - ❌ Failed to send email to hesbonwere7@gmail.com: [WinError 10054] An existing connection was forcibly closed by the remote host
2026-09-16 16:23:47,059 - ERROR - [211/243] FAILED -> Hesbon were <hesbonwere7@gmail.com>
2026-09-16 16:23:48,698 - ERROR - ❌ Failed to send email to abedmwanzia04@gmail.com: [WinError 10054] An existing connection was forcibly closed by the remote host
2026-09-16 16:23:48,698 - ERROR - [212/243] FAILED -> MICHAEL JUNIOR <abedmwanzia04@gmail.com>
2026-09-16 16:23:50,402 - ERROR - ❌ Failed to send email to naftalibrevyl@gmail.com: [WinError 10054] An existing connection was forcibly closed by the remote host
2026-09-16 16:23:50,403 - ERROR - [213/243] FAILED -> Naftali BREVYL <naftalibrevyl@gmail.com>
2026-09-16 16:23:52,030 - ERROR - ❌ Failed to send email to bgichana2000@gmail.com: [WinError 10054] An existing connection was forcibly closed by the remote host
2026-09-16 16:23:52,031 - ERROR - [214/243] FAILED -> Prince Ben <bgichana2000@gmail.com>
2026-09-16 16:23:53,924 - ERROR - ❌ Failed to send email to dylanmabeya034@gmail.com: [WinError 10054] An existing connection was forcibly closed by the remote host
2026-09-16 16:23:53,925 - ERROR - [215/243] FAILED -> Mabeya <dylanmabeya034@gmail.com>
2026-09-16 16:23:57,515 - ERROR - ❌ Failed to send email to onyangoleenus@gmail.com: [WinError 10054] An existing connection was forcibly closed by the remote host
2026-09-16 16:23:57,516 - ERROR - [216/243] FAILED -> Leenus Onyango <onyangoleenus@gmail.com>
2026-09-16 16:23:59,575 - ERROR - ❌ Failed to send email to dheebidder254@gmail.com: [WinError 10054] An existing connection was forcibly closed by the remote host
2026-09-16 16:23:59,576 - ERROR - [217/243] FAILED -> Omar DheeBidder <dheebidder254@gmail.com>
2026-09-16 16:24:01,338 - ERROR - ❌ Failed to send email to otienoamos005@gmail.com: [WinError 10054] An existing connection was forcibly closed by the remote host
2026-09-16 16:24:01,339 - ERROR - [218/243] FAILED -> Amos <otienoamos005@gmail.com>
2026-09-16 16:24:03,168 - ERROR - ❌ Failed to send email to mu.tethiaa254@gmail.com: [WinError 10054] An existing connection was forcibly closed by the remote host
2026-09-16 16:24:03,168 - ERROR - [219/243] FAILED -> Kenneth <mu.tethiaa254@gmail.com>
2026-09-16 16:24:04,801 - ERROR - ❌ Failed to send email to clown7448@gmail.com: [WinError 10054] An existing connection was forcibly closed by the remote host
2026-09-16 16:24:04,802 - ERROR - [220/243] FAILED -> Elias <clown7448@gmail.com>
2026-09-16 16:24:06,476 - ERROR - ❌ Failed to send email to japhethogola727@gmail.com: [WinError 10054] An existing connection was forcibly closed by the remote host
2026-09-16 16:24:06,476 - ERROR - [221/243] FAILED -> Japheth Ogola <japhethogola727@gmail.com>
2026-09-16 16:24:08,177 - ERROR - ❌ Failed to send email to rastowakhungu2@gmail.com.amr: [WinError 10054] An existing connection was forcibly closed by the remote host
2026-09-16 16:24:08,178 - ERROR - [222/243] FAILED -> Rasto Wakhungu <rastowakhungu2@gmail.com.amr>
2026-09-16 16:24:10,098 - ERROR - ❌ Failed to send email to omarhalfwayback@gmail.com: [WinError 10054] An existing connection was forcibly closed by the remote host
2026-09-16 16:24:10,099 - ERROR - [223/243] FAILED -> Omar DheeBidder <omarhalfwayback@gmail.com>
2026-09-16 16:24:12,192 - ERROR - ❌ Failed to send email to poetryseller@gmail.com: [WinError 10054] An existing connection was forcibly closed by the remote host
2026-09-16 16:24:12,193 - ERROR - [224/243] FAILED -> Tom <poetryseller@gmail.com>
2026-09-16 16:24:14,024 - ERROR - ❌ Failed to send email to mikekarau478@gmail.com: [WinError 10054] An existing connection was forcibly closed by the remote host
2026-09-16 16:24:14,025 - ERROR - [225/243] FAILED -> Mike wanjiru <mikekarau478@gmail.com>
2026-09-16 16:24:15,726 - ERROR - ❌ Failed to send email to johnamulwani093@gmail.com: [WinError 10054] An existing connection was forcibly closed by the remote host
2026-09-16 16:24:15,726 - ERROR - [226/243] FAILED -> Yssel <johnamulwani093@gmail.com>
2026-09-16 16:24:17,391 - ERROR - ❌ Failed to send email to ishmaelamasia3@gmail.com: [WinError 10054] An existing connection was forcibly closed by the remote host
2026-09-16 16:24:17,391 - ERROR - [227/243] FAILED -> View Once <ishmaelamasia3@gmail.com>
2026-09-16 16:24:19,523 - ERROR - ❌ Failed to send email to odoyorolex40@gmail.com: [WinError 10054] An existing connection was forcibly closed by the remote host
2026-09-16 16:24:19,523 - ERROR - [228/243] FAILED -> Rolo Rolex <odoyorolex40@gmail.com>
2026-09-16 16:24:21,578 - ERROR - ❌ Failed to send email to winniekhayumbi@gmail.com: [WinError 10054] An existing connection was forcibly closed by the remote host
2026-09-16 16:24:21,578 - ERROR - [229/243] FAILED -> Winny Zipporah Khayumbi <winniekhayumbi@gmail.com>
2026-09-16 16:24:37,057 - ERROR - ❌ Failed to send email to ryanominde01@gmail.com: [WinError 10054] An existing connection was forcibly closed by the remote host
2026-09-16 16:24:37,059 - ERROR - [230/243] FAILED -> Ryan Gigs <ryanominde01@gmail.com>
"""

def extract_failed_emails(log_text):
    # Regex to find: ❌ Failed to send email to whatever@gmail.com:
    pattern = r"Failed to send email to ([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}):"
    matches = re.findall(pattern, log_text)
    # Deduplicate while preserving order
    unique_emails = []
    for email in matches:
        if email not in unique_emails:
            unique_emails.append(email)
    return unique_emails

def run():
    failed_emails = extract_failed_emails(raw_log_text)
    
    if not failed_emails:
        logger.error("No failed emails parsed from the log text. Aborting.")
        return
        
    logger.info("=" * 60)
    logger.info(f"  FYM Promo Retry Mailer - Starting Up for {len(failed_emails)} Users")
    logger.info("=" * 60)

    initialize_firebase()
    all_profiles = get_all_profiles()

    if not all_profiles:
        logger.error("No profiles found in DB. Aborting.")
        return
        
    # Map profiles by email for quick lookup
    profiles_by_email = {}
    for p in all_profiles:
        em = p.get('email', '').strip()
        if em:
            profiles_by_email[em] = p

    sent = failed = 0
    DELAY_SECONDS = 1.5

    for idx, target_email in enumerate(failed_emails, 1):
        user = profiles_by_email.get(target_email, {})
        name = user.get("name") or user.get("username") or "there"
        
        # We know it failed due to WinError 10054 (connection drop).
        # We will attempt to resend it.
        try:
            if send_update_promo_email(target_email, name):
                logger.info(f"[{idx}/{len(failed_emails)}] ✅ RETRY SUCCESS -> {name} <{target_email}>")
                sent += 1
            else:
                logger.error(f"[{idx}/{len(failed_emails)}] ❌ RETRY FAILED -> {name} <{target_email}>")
                failed += 1
        except Exception as e:
            logger.error(f"[{idx}/{len(failed_emails)}] ❌ EXCEPTION -> {target_email} - {str(e)}")
            failed += 1
            
        # Slightly longer delay to avoid aggressive rate-limiting causing connection closures
        time.sleep(2.0)

    logger.info("=" * 60)
    logger.info("  RETRY BROADCAST COMPLETE")
    logger.info(f"  Sent: {sent}   Failed: {failed}")
    logger.info("=" * 60)

if __name__ == "__main__":
    run()
