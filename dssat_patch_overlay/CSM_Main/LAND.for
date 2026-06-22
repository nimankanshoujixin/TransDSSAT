C=======================================================================
C COPYRIGHT 1998-2024
C                     DSSAT Foundation
C                     University of Florida, Gainesville, Florida
C                     International Fertilizer Development Center
C                     
C ALL RIGHTS RESERVED
C=======================================================================
C=======================================================================
C  LAND UNIT Module. G.Hoogenboom, J.W.Jones, C.Porter
C-----------------------------------------------------------------------
C  Land Unit Module.  Provides the interface between soil, weather
C  and crops.  Based on the original CROPGRO routine
C=======================================================================
C  REVISION       HISTORY
C  12/01/2001 CHP Written.
C  12/12/2001 GH  Rename to Land
!  10/24/2005 CHP Put weather variables in constructed variable. 
!  02/28/2006 CHP Rename Alt_Plant to Plant, move call to CROPGRO there
!  03/03/2006 CHP Added tillage (A.Andales & WDBatchelor).
!  03/21/2006 CHP Added mulch effects
!  10/31/2007 CHP Added simple K model.

C=======================================================================
      SUBROUTINE LAND(CONTROL, ISWITCH, 
     &                YRPLT, MDATE, YREND)
      
C-----------------------------------------------------------------------
      USE ModuleDefs      
      USE FloodModule      
      USE CsvOutput   ! VSH 

      IMPLICIT NONE
      EXTERNAL INFO, ERROR, WARNING, IPIBS, WEATHR, SOIL, SPAM, PLANT, 
     &  OPSUM, MGMTOPS, TDINT_BOOTSTRAP, TDINT_WAIT_ACTION,
     &  TDINT_WRITE_READY, TDINT_WRITE_STEP_RESPONSE,
     &  TDINT_WRITE_CLOSE_OUTCOME
      SAVE
C-----------------------------------------------------------------------
C     Crop, Experiment, Command line Variables
C-----------------------------------------------------------------------
      CHARACTER*2  CROP
      CHARACTER*6  ERRKEY
      PARAMETER   (ERRKEY = 'LAND  ')
      CHARACTER*8  MODEL
      CHARACTER*30 FILEIO
      
C-----------------------------------------------------------------------
C     Date / Timing / Sequencing Variables
C-----------------------------------------------------------------------
      INTEGER      DYNAMIC, YRSIM, YRDOY

C-----------------------------------------------------------------------
C     Input and Output Handling
C-----------------------------------------------------------------------
      CHARACTER*1  IDETS, IPLTI
      CHARACTER*78 MSG(2)
      LOGICAL TDINT_INIT, TDINT_ON, TDINT_READY, TDINT_CLOSE
      INTEGER TDINT_STEP, TDINT_DEC, TDINT_DAYS_DONE
      REAL TDINT_IRR, TDINT_N
      CHARACTER*240 TDINT_HELPER
      COMMON /TDINTCOM/ TDINT_INIT, TDINT_ON, TDINT_READY,
     &  TDINT_CLOSE, TDINT_STEP, TDINT_DEC, TDINT_DAYS_DONE,
     &  TDINT_IRR, TDINT_N, TDINT_HELPER
      SAVE /TDINTCOM/
      DATA TDINT_INIT /.FALSE./, TDINT_ON /.FALSE./
      DATA TDINT_READY /.FALSE./, TDINT_CLOSE /.FALSE./
      DATA TDINT_STEP /0/, TDINT_DEC /0/, TDINT_DAYS_DONE /0/
      DATA TDINT_IRR /0.0/, TDINT_N /0.0/
      DATA TDINT_HELPER /' '/

C-----------------------------------------------------------------------
C     Weather module Variables
C-----------------------------------------------------------------------
      TYPE (WeatherType)  WEATHER

C-----------------------------------------------------------------------
C     Soil Processes Module Variables 
C-----------------------------------------------------------------------
      REAL SNOW, WINF
      REAL, DIMENSION(NL) :: NH4_plant, NO3_plant, SPi_Avail, SKi_Avail
      REAL, DIMENSION(NL) :: ST, UPPM, SW, SWDELTS, UPFLOW
      TYPE (SoilType) SOILPROP    !type defined in ModuleDefs
      TYPE (FloodWatType) FLOODWAT
      TYPE (FloodNType)   FloodN
      TYPE (MulchType)    MULCH
!     Needed for ORYZA-Rice
      REAL, DIMENSION(0:NL) :: SomLitC
      REAL, DIMENSION(0:NL,NELEM) :: SomLitE

C-----------------------------------------------------------------------
C     Soil - Plant - Atmosphere Module Variables
C-----------------------------------------------------------------------
      REAL EO, EOP, ES, SRFTEMP, TRWUP
      REAL SWDELTU(NL), SWDELTX(NL) !, RWU(NL)
!     Needed for CaneGro_SA
      REAL EOS, EP, TRWU
!     Calculated by ORYZA-Rice
      REAL UH2O(NL)
!     Needed for SALUS
      REAL RWU(NL)

C-----------------------------------------------------------------------
C     PLANT Module Variables
C-----------------------------------------------------------------------
      INTEGER MDATE
      INTEGER STGDOY(20)
      REAL CANHT, EORATIO, NSTRES, PORMIN, PSTRES1, RWUMX
      REAL XHLAI, XLAI
      REAL KSEVAP, KTRANS
      REAL, Dimension(NL) :: PUptake, RLV, FracRts, UNH4, UNO3, KUptake
      Type (ResidueType) HARVRES  !type defined in ModuleDefs
      Type (ResidueType) SENESCE  
      
C-----------------------------------------------------------------------
C     Operations Management Module Variables 
C-----------------------------------------------------------------------
      TYPE (TillType) TILLVALS
      INTEGER YREND, YRPLT
      REAL IRRAMT
      REAL, DIMENSION(2) :: HARVFRAC   !Harvest & byproduct fractions
      TYPE (FertType) FERTDATA         !Fertilizer application
      TYPE (OrgMatAppType)OMAData      !Organic matter application

C-----------------------------------------------------------------------
!!     Temporary timer function
!!     Date / time variables
!      INTEGER DATE_TIME(8)
!!      date_time(1)  The 4-digit year  
!!      date_time(2)  The month of the year  
!!      date_time(3)  The day of the month  
!!      date_time(4)  The time difference with respect to Coordinated Universal Time (UTC) in minutes  
!!      date_time(5)  The hour of the day (range 0 to 23) - local time  
!!      date_time(6)  The minutes of the hour (range 0 to 59) - local time  
!!      date_time(7)  The seconds of the minute (range 0 to 59) - local time  
!!      date_time(8)  The milliseconds of the second (range 0 to 999) - local time  
!      REAL TIME0, TIME1, TIME_START DELTA_TIME
C-----------------------------------------------------------------------

C     Define constructed variable types based on definitions in
C     ModuleDefs.for.
      TYPE (ControlType) CONTROL
      TYPE (SwitchType)  ISWITCH

C     Transfer values from constructed data types into local variables.
      CROP    = CONTROL % CROP
      DYNAMIC = CONTROL % DYNAMIC
      FILEIO  = CONTROL % FILEIO
      MODEL   = CONTROL % MODEL
      YRDOY   = CONTROL % YRDOY
      YRSIM   = CONTROL % YRSIM

      IPLTI   = ISWITCH % IPLTI
      CALL TDINT_BOOTSTRAP(TDINT_INIT, TDINT_ON, TDINT_HELPER)

C***********************************************************************
C***********************************************************************
C     Run Initialization - Called once per simulation
C***********************************************************************
      IF (DYNAMIC .EQ. RUNINIT) THEN
C-----------------------------------------------------------------------
!!     Temporary timer function
!      !Get initial time
!      CALL DATE_AND_TIME (VALUES=DATE_TIME)
!!     Convert time to seconds
!      TIME0 = DATE_TIME(7) 
!     &      + DATE_TIME(8) / 1000.  
!     &      + DATE_TIME(6) * 60.  
!     &      + DATE_TIME(5) * 3600.
!      TIME_START = TIME0
C-----------------------------------------------------------------------
C     Read switches from FILEIO
C-----------------------------------------------------------------------
      CALL IPIBS (CONTROL, ISWITCH, CROP, IDETS, MODEL)

C-----------------------------------------------------------------------
C     Read input parameters for weather routines
C-----------------------------------------------------------------------
      CALL WEATHR(CONTROL, ISWITCH, WEATHER, YREND)

C-----------------------------------------------------------------------
C     Read initial soil data 
C-----------------------------------------------------------------------
      CALL SOIL(CONTROL, ISWITCH, 
     &    ES, FERTDATA, FracRts, HARVRES, IRRAMT,         !Input
     &    KTRANS, KUptake, OMAData, PUptake, RLV,         !Input
     &    SENESCE, ST, SWDELTX,TILLVALS, UNH4, UNO3,      !Input
     &    WEATHER, XHLAI,                                 !Input
     &    FLOODN, FLOODWAT, MULCH, UPFLOW,                !I/O
     &    NH4_plant, NO3_plant, SKi_AVAIL, SNOW,          !Output
     &    SPi_AVAIL, SOILPROP, SomLitC, SomLitE,          !Output
     &    SW, SWDELTS, SWDELTU, UPPM, WINF, YREND)        !Output

C-----------------------------------------------------------------------
C     Read initial soil-plant-atmosphere data
C-----------------------------------------------------------------------
      CALL SPAM(CONTROL, ISWITCH,
     &    CANHT, EORATIO, KSEVAP, KTRANS, MULCH,          !Input
     &    PSTRES1, PORMIN, RLV, RWUMX, SOILPROP, SW,      !Input
     &    SWDELTS, UH2O, WEATHER, WINF, XHLAI, XLAI,      !Input
     &    FLOODWAT, SWDELTU,                              !I/O
     &    EO, EOP, EOS, EP, ES, RWU, SRFTEMP, ST,         !Output
     &    SWDELTX, TRWU, TRWUP, UPFLOW)                   !Output

C-----------------------------------------------------------------------
C     Read initial plant module data
C-----------------------------------------------------------------------
      CALL PLANT(CONTROL, ISWITCH, 
     &    EO, EOP, EOS, EP, ES, FLOODWAT, HARVFRAC,       !Input
     &    IRRAMT, NH4_plant, NO3_plant, SKi_Avail,        !Input
     &    SPi_AVAIL, SNOW, SOILPROP, SRFTEMP, ST, SW,     !Input
     &    TRWUP, WEATHER, YREND, YRPLT,                   !Input
     &    FLOODN,                                         !I/O
     &    CANHT, EORATIO, HARVRES, KSEVAP, KTRANS,        !Output
     &    KUptake, MDATE, NSTRES, PSTRES1,                !Output
     &    PUptake, PORMIN, RLV, RWUMX, SENESCE,           !Output
     &    STGDOY, FracRts, UH2O, UNH4, UNO3, XHLAI, XLAI) !Output

C-----------------------------------------------------------------------
C     Initialize summary.out information
C-----------------------------------------------------------------------
      CALL OPSUM (CONTROL, ISWITCH, YRPLT)

C*********************************************************************** 
C*********************************************************************** 
C     SEASONAL INITIALIZATION
C*********************************************************************** 
      ELSEIF (DYNAMIC .EQ. SEASINIT) THEN
C-----------------------------------------------------------------------
C     Call WEATHR for initialization - reads first day of weather
C     data for use in soil N and soil temp initialization.
C-----------------------------------------------------------------------
      CALL WEATHR(CONTROL, ISWITCH, WEATHER, YREND)

C-----------------------------------------------------------------------
C     Set planting date, adjust operations dates for seasonal or 
C     sequenced runs.
C-----------------------------------------------------------------------
      CALL MGMTOPS(CONTROL, ISWITCH, 
     &    FLOODWAT, HARVRES, SOILPROP, ST,                !Input 
     &    STGDOY, SW, WEATHER,                            !Input
     &    YREND, FERTDATA, HARVFRAC, IRRAMT,              !Output
     &    MDATE, OMADATA, TILLVALS, YRPLT)                !Output

C-----------------------------------------------------------------------
      IF (YRPLT < YRSIM .AND. CROP /= 'FA' .AND.
     &    INDEX('AF', IPLTI) == 0) THEN
          CALL ERROR(ERRKEY,2,' ',0)
      ENDIF

C-----------------------------------------------------------------------
C     Seasonal initialization for soil processes
C-----------------------------------------------------------------------
      CALL SOIL(CONTROL, ISWITCH, 
     &    ES, FERTDATA, FracRts, HARVRES, IRRAMT,         !Input
     &    KTRANS, KUptake, OMAData, PUptake, RLV,         !Input
     &    SENESCE, ST, SWDELTX,TILLVALS, UNH4, UNO3,      !Input
     &    WEATHER, XHLAI,                                 !Input
     &    FLOODN, FLOODWAT, MULCH, UPFLOW,                !I/O
     &    NH4_plant, NO3_plant, SKi_AVAIL, SNOW,          !Output
     &    SPi_AVAIL, SOILPROP, SomLitC, SomLitE,          !Output
     &    SW, SWDELTS, SWDELTU, UPPM, WINF, YREND)        !Output

C-----------------------------------------------------------------------
C     Seasonal initialization for soil-plant-atmosphere processes
!     chp moved this before SOIL, so soil temp is available 
!     update 2020-12-04 - order makes no difference
C-----------------------------------------------------------------------
      CALL SPAM(CONTROL, ISWITCH,
     &    CANHT, EORATIO, KSEVAP, KTRANS, MULCH,          !Input
     &    PSTRES1, PORMIN, RLV, RWUMX, SOILPROP, SW,      !Input
     &    SWDELTS, UH2O, WEATHER, WINF, XHLAI, XLAI,      !Input
     &    FLOODWAT, SWDELTU,                              !I/O
     &    EO, EOP, EOS, EP, ES, RWU, SRFTEMP, ST,         !Output
     &    SWDELTX, TRWU, TRWUP, UPFLOW)                   !Output

C-----------------------------------------------------------------------
C     Initialize PLANT routines (including phenology and pest)
C-----------------------------------------------------------------------
      CALL PLANT(CONTROL, ISWITCH, 
     &    EO, EOP, EOS, EP, ES, FLOODWAT, HARVFRAC,       !Input
     &    IRRAMT, NH4_plant, NO3_plant, SKi_Avail,        !Input
     &    SPi_AVAIL, SNOW, SOILPROP, SRFTEMP, ST, SW,     !Input
     &    TRWUP, WEATHER, YREND, YRPLT,                   !Input
     &    FLOODN,                                         !I/O
     &    CANHT, EORATIO, HARVRES, KSEVAP, KTRANS,        !Output
     &    KUptake, MDATE, NSTRES, PSTRES1,                !Output
     &    PUptake, PORMIN, RLV, RWUMX, SENESCE,           !Output
     &    STGDOY, FracRts, UH2O, UNH4, UNO3, XHLAI, XLAI) !Output

C-----------------------------------------------------------------------
C     Initialize summary output file - possible output from 
C     various modules.
C-----------------------------------------------------------------------
      IF (IDETS .EQ. 'Y' .OR. IDETS .EQ. 'A') THEN
        CALL OPSUM (CONTROL, ISWITCH, YRPLT)
      ENDIF

      IF (TDINT_ON .AND. .NOT. TDINT_READY) THEN
        CALL TDINT_WRITE_READY(TDINT_HELPER, CONTROL % DAS, MDATE,
     &    SOILPROP, SW, NH4_plant, NO3_plant, WEATHER, XLAI,
     &    PSTRES1, NSTRES, EOP)
        TDINT_READY = .TRUE.
        TDINT_STEP = 0
        TDINT_DEC = 0
        TDINT_DAYS_DONE = 0
        TDINT_CLOSE = .FALSE.
      ENDIF

C***********************************************************************
C***********************************************************************
C     DAILY RATE CALCULATIONS
C***********************************************************************
      ELSE IF (DYNAMIC .EQ. RATE) THEN
C-----------------------------------------------------------------------
C     Call WEATHER Subroutine to input weather data and to
C     calculate hourly radiation and air temperature values
C     Note: First day of weather has already been read by 
C       initialization call to WEATHR.
C-----------------------------------------------------------------------
      CALL WEATHR(CONTROL, ISWITCH, WEATHER, YREND)

      IF (TDINT_ON .AND. TDINT_DEC .LE. 0) THEN
        CALL TDINT_WAIT_ACTION(TDINT_HELPER, CONTROL % DAS, MDATE,
     &    SOILPROP, SW, NH4_plant, NO3_plant, WEATHER, XLAI,
     &    PSTRES1, NSTRES, EOP, TDINT_STEP, TDINT_DEC,
     &    TDINT_IRR, TDINT_N, TDINT_CLOSE)
        IF (TDINT_CLOSE) THEN
          YREND = YRDOY
        ELSEIF (TDINT_DEC .LE. 0) THEN
          TDINT_DEC = 1
        ENDIF
      ENDIF

C-----------------------------------------------------------------------
C     Call Operations Management module to determine today's 
C     applications of irrigation, tillage, etc.
C-----------------------------------------------------------------------
      CALL MGMTOPS(CONTROL, ISWITCH, 
     &    FLOODWAT, HARVRES, SOILPROP, ST,                !Input 
     &    STGDOY, SW, WEATHER,                            !Input
     &    YREND, FERTDATA, HARVFRAC, IRRAMT,              !Output
     &    MDATE, OMADATA, TILLVALS, YRPLT)                !Output

      IF (TDINT_ON .AND. .NOT. TDINT_CLOSE .AND. TDINT_DEC .GT. 0)
     &  THEN
        TDINT_DEC = TDINT_DEC - 1
        TDINT_DAYS_DONE = TDINT_DAYS_DONE + 1
        IF (TDINT_DEC .LE. 0 .OR.
     &      (YREND .GT. 0 .AND. YRDOY .GE. YREND)) THEN
          CALL TDINT_WRITE_STEP_RESPONSE(TDINT_HELPER, CONTROL % DAS,
     &      MDATE, SOILPROP, SW, NH4_plant, NO3_plant, WEATHER,
     &      XLAI, PSTRES1, NSTRES, EOP, TDINT_STEP, TDINT_DAYS_DONE,
     &      YREND .GT. 0 .AND. YRDOY .GE. YREND)
          TDINT_STEP = TDINT_STEP + 1
          TDINT_DEC = 0
          TDINT_DAYS_DONE = 0
        ENDIF
      ENDIF

C-----------------------------------------------------------------------
C     Call Soil processes module to determine today's rates of 
C     change of soil properties.
C-----------------------------------------------------------------------
      CALL SOIL(CONTROL, ISWITCH, 
     &    ES, FERTDATA, FracRts, HARVRES, IRRAMT,         !Input
     &    KTRANS, KUptake, OMAData, PUptake, RLV,         !Input
     &    SENESCE, ST, SWDELTX,TILLVALS, UNH4, UNO3,      !Input
     &    WEATHER, XHLAI,                                 !Input
     &    FLOODN, FLOODWAT, MULCH, UPFLOW,                !I/O
     &    NH4_plant, NO3_plant, SKi_AVAIL, SNOW,          !Output
     &    SPi_AVAIL, SOILPROP, SomLitC, SomLitE,          !Output
     &    SW, SWDELTS, SWDELTU, UPPM, WINF, YREND)        !Output

C-----------------------------------------------------------------------
C     Call Soil-plant-atmosphere module to determine today's
C     rates of evapotranspiration.
C-----------------------------------------------------------------------
      CALL SPAM(CONTROL, ISWITCH,
     &    CANHT, EORATIO, KSEVAP, KTRANS, MULCH,          !Input
     &    PSTRES1, PORMIN, RLV, RWUMX, SOILPROP, SW,      !Input
     &    SWDELTS, UH2O, WEATHER, WINF, XHLAI, XLAI,      !Input
     &    FLOODWAT, SWDELTU,                              !I/O
     &    EO, EOP, EOS, EP, ES, RWU, SRFTEMP, ST,         !Output
     &    SWDELTX, TRWU, TRWUP, UPFLOW)                   !Output

C-----------------------------------------------------------------------
C     Call PLANT Subroutine to calculate crop growth and
C     development rates.
C     Skip plant growth and development routines for fallow runs
C-----------------------------------------------------------------------
!      IF (CROP .NE. 'FA' .AND. 
!     &    YRDOY .GE. YRPLT .AND. YRPLT .NE. -99) THEN
        CALL PLANT(CONTROL, ISWITCH, 
     &    EO, EOP, EOS, EP, ES, FLOODWAT, HARVFRAC,       !Input
     &    IRRAMT, NH4_plant, NO3_plant, SKi_Avail,        !Input
     &    SPi_AVAIL, SNOW, SOILPROP, SRFTEMP, ST, SW,     !Input
     &    TRWUP, WEATHER, YREND, YRPLT,                   !Input
     &    FLOODN,                                         !I/O
     &    CANHT, EORATIO, HARVRES, KSEVAP, KTRANS,        !Output
     &    KUptake, MDATE, NSTRES, PSTRES1,                !Output
     &    PUptake, PORMIN, RLV, RWUMX, SENESCE,           !Output
     &    STGDOY, FracRts, UH2O, UNH4, UNO3, XHLAI, XLAI) !Output
!      ENDIF

C***********************************************************************
C     DAILY INTEGRATION 
C***********************************************************************
      ELSE IF (DYNAMIC .EQ. INTEGR) THEN
C***********************************************************************
C     Integrate soil state variables
C-----------------------------------------------------------------------
      CALL SOIL(CONTROL, ISWITCH, 
     &    ES, FERTDATA, FracRts, HARVRES, IRRAMT,         !Input
     &    KTRANS, KUptake, OMAData, PUptake, RLV,         !Input
     &    SENESCE, ST, SWDELTX,TILLVALS, UNH4, UNO3,      !Input
     &    WEATHER, XHLAI,                                 !Input
     &    FLOODN, FLOODWAT, MULCH, UPFLOW,                !I/O
     &    NH4_plant, NO3_plant, SKi_AVAIL, SNOW,          !Output
     &    SPi_AVAIL, SOILPROP, SomLitC, SomLitE,          !Output
     &    SW, SWDELTS, SWDELTU, UPPM, WINF, YREND)        !Output

C-----------------------------------------------------------------------
C     Compute cumulative totals for soil-plant-atmosphere processes
C-----------------------------------------------------------------------
      CALL SPAM(CONTROL, ISWITCH,
     &    CANHT, EORATIO, KSEVAP, KTRANS, MULCH,          !Input
     &    PSTRES1, PORMIN, RLV, RWUMX, SOILPROP, SW,      !Input
     &    SWDELTS, UH2O, WEATHER, WINF, XHLAI, XLAI,      !Input
     &    FLOODWAT, SWDELTU,                              !I/O
     &    EO, EOP, EOS, EP, ES, RWU, SRFTEMP, ST,         !Output
     &    SWDELTX, TRWU, TRWUP, UPFLOW)                   !Output

C-----------------------------------------------------------------------
C     Call Plant module to integrate daily plant processes and update
C     plant state variables.
C-----------------------------------------------------------------------
      IF (CROP .NE. 'FA' .AND. 
     &        YRDOY .GE. YRPLT .AND. YRPLT .NE. -99) THEN
        CALL PLANT(CONTROL, ISWITCH, 
     &    EO, EOP, EOS, EP, ES, FLOODWAT, HARVFRAC,       !Input
     &    IRRAMT, NH4_plant, NO3_plant, SKi_Avail,        !Input
     &    SPi_AVAIL, SNOW, SOILPROP, SRFTEMP, ST, SW,     !Input
     &    TRWUP, WEATHER, YREND, YRPLT,                   !Input
     &    FLOODN,                                         !I/O
     &    CANHT, EORATIO, HARVRES, KSEVAP, KTRANS,        !Output
     &    KUptake, MDATE, NSTRES, PSTRES1,                !Output
     &    PUptake, PORMIN, RLV, RWUMX, SENESCE,           !Output
     &    STGDOY, FracRts, UH2O, UNH4, UNO3, XHLAI, XLAI) !Output
      ENDIF

C-----------------------------------------------------------------------
C     Call Operations Management module to check for harvest end, 
C     accumulate variables.
C-----------------------------------------------------------------------
      CALL MGMTOPS(CONTROL, ISWITCH, 
     &    FLOODWAT, HARVRES, SOILPROP, ST,                !Input 
     &    STGDOY, SW, WEATHER,                            !Input
     &    YREND, FERTDATA, HARVFRAC, IRRAMT,              !Output
     &    MDATE, OMADATA, TILLVALS, YRPLT)                !Output

C***********************************************************************
C***********************************************************************
C     Daily Output
C***********************************************************************
      ELSE IF (DYNAMIC .EQ. OUTPUT) THEN

      CALL WEATHR(CONTROL, ISWITCH, WEATHER, YREND)

        CALL SOIL(CONTROL, ISWITCH, 
     &    ES, FERTDATA, FracRts, HARVRES, IRRAMT,         !Input
     &    KTRANS, KUptake, OMAData, PUptake, RLV,         !Input
     &    SENESCE, ST, SWDELTX,TILLVALS, UNH4, UNO3,      !Input
     &    WEATHER, XHLAI,                                 !Input
     &    FLOODN, FLOODWAT, MULCH, UPFLOW,                !I/O
     &    NH4_plant, NO3_plant, SKi_AVAIL, SNOW,          !Output
     &    SPi_AVAIL, SOILPROP, SomLitC, SomLitE,          !Output
     &    SW, SWDELTS, SWDELTU, UPPM, WINF, YREND)        !Output

        CALL SPAM(CONTROL, ISWITCH,
     &    CANHT, EORATIO, KSEVAP, KTRANS, MULCH,          !Input
     &    PSTRES1, PORMIN, RLV, RWUMX, SOILPROP, SW,      !Input
     &    SWDELTS, UH2O, WEATHER, WINF, XHLAI, XLAI,      !Input
     &    FLOODWAT, SWDELTU,                              !I/O
     &    EO, EOP, EOS, EP, ES, RWU, SRFTEMP, ST,         !Output
     &    SWDELTX, TRWU, TRWUP, UPFLOW)                   !Output

C-----------------------------------------------------------------------
C     Call plant module for daily printout.
C-----------------------------------------------------------------------
        IF (CROP .NE. 'FA') THEN
          CALL PLANT(CONTROL, ISWITCH, 
     &    EO, EOP, EOS, EP, ES, FLOODWAT, HARVFRAC,       !Input
     &    IRRAMT, NH4_plant, NO3_plant, SKi_Avail,        !Input
     &    SPi_AVAIL, SNOW, SOILPROP, SRFTEMP, ST, SW,     !Input
     &    TRWUP, WEATHER, YREND, YRPLT,                   !Input
     &    FLOODN,                                         !I/O
     &    CANHT, EORATIO, HARVRES, KSEVAP, KTRANS,        !Output
     &    KUptake, MDATE, NSTRES, PSTRES1,                !Output
     &    PUptake, PORMIN, RLV, RWUMX, SENESCE,           !Output
     &    STGDOY, FracRts, UH2O, UNH4, UNO3, XHLAI, XLAI) !Output
        ENDIF

        CALL MGMTOPS(CONTROL, ISWITCH, 
     &    FLOODWAT, HARVRES, SOILPROP, ST,                !Input 
     &    STGDOY, SW, WEATHER,                            !Input
     &    YREND, FERTDATA, HARVFRAC, IRRAMT,              !Output
     &    MDATE, OMADATA, TILLVALS, YRPLT)                !Output

C*********************************************************************** 
C***********************************************************************
C     Seasonal Output
C*********************************************************************** 
      ELSE IF (DYNAMIC .EQ. SEASEND) THEN

C     Call WEATHER module to close current weather file 
      CALL WEATHR(CONTROL, ISWITCH, WEATHER, YREND)

C     Print seasonal summaries and close files.
      CALL SOIL(CONTROL, ISWITCH, 
     &    ES, FERTDATA, FracRts, HARVRES, IRRAMT,         !Input
     &    KTRANS, KUptake, OMAData, PUptake, RLV,         !Input
     &    SENESCE, ST, SWDELTX,TILLVALS, UNH4, UNO3,      !Input
     &    WEATHER, XHLAI,                                 !Input
     &    FLOODN, FLOODWAT, MULCH, UPFLOW,                !I/O
     &    NH4_plant, NO3_plant, SKi_AVAIL, SNOW,          !Output
     &    SPi_AVAIL, SOILPROP, SomLitC, SomLitE,          !Output
     &    SW, SWDELTS, SWDELTU, UPPM, WINF, YREND)        !Output

      CALL SPAM(CONTROL, ISWITCH,
     &    CANHT, EORATIO, KSEVAP, KTRANS, MULCH,          !Input
     &    PSTRES1, PORMIN, RLV, RWUMX, SOILPROP, SW,      !Input
     &    SWDELTS, UH2O, WEATHER, WINF, XHLAI, XLAI,      !Input
     &    FLOODWAT, SWDELTU,                              !I/O
     &    EO, EOP, EOS, EP, ES, RWU, SRFTEMP, ST,         !Output
     &    SWDELTX, TRWU, TRWUP, UPFLOW)                   !Output

      CALL PLANT(CONTROL, ISWITCH, 
     &    EO, EOP, EOS, EP, ES, FLOODWAT, HARVFRAC,       !Input
     &    IRRAMT, NH4_plant, NO3_plant, SKi_Avail,        !Input
     &    SPi_AVAIL, SNOW, SOILPROP, SRFTEMP, ST, SW,     !Input
     &    TRWUP, WEATHER, YREND, YRPLT,                   !Input
     &    FLOODN,                                         !I/O
     &    CANHT, EORATIO, HARVRES, KSEVAP, KTRANS,        !Output
     &    KUptake, MDATE, NSTRES, PSTRES1,                !Output
     &    PUptake, PORMIN, RLV, RWUMX, SENESCE,           !Output
     &    STGDOY, FracRts, UH2O, UNH4, UNO3, XHLAI, XLAI) !Output

!     Call management operations module for seasonal printout.
      CALL MGMTOPS(CONTROL, ISWITCH, 
     &    FLOODWAT, HARVRES, SOILPROP, ST,                !Input 
     &    STGDOY, SW, WEATHER,                            !Input
     &    YREND, FERTDATA, HARVFRAC, IRRAMT,              !Output
     &    MDATE, OMADATA, TILLVALS, YRPLT)                !Output

C-----------------------------------------------------------------------
C     Seasonal Output
C     Call end of season and summary output subroutines
C-----------------------------------------------------------------------
      CALL OPSUM (CONTROL, ISWITCH, YRPLT)

      IF (TDINT_ON) THEN
        IF (.NOT. TDINT_CLOSE .AND.
     &      (TDINT_DAYS_DONE .GT. 0 .OR. TDINT_DEC .GT. 0)) THEN
          CALL TDINT_WRITE_STEP_RESPONSE(TDINT_HELPER, CONTROL % DAS,
     &      MDATE, SOILPROP, SW, NH4_plant, NO3_plant, WEATHER,
     &      XLAI, PSTRES1, NSTRES, EOP, TDINT_STEP, TDINT_DAYS_DONE,
     &      .TRUE.)
          TDINT_STEP = TDINT_STEP + 1
          TDINT_DEC = 0
          TDINT_DAYS_DONE = 0
        ENDIF
        CALL TDINT_WRITE_CLOSE_OUTCOME(TDINT_HELPER)
      ENDIF

!!     Temporary timer function
!      CALL DATE_AND_TIME (VALUES=DATE_TIME)
!      
!!     Convert time to seconds
!      TIME1 = DATE_TIME(7) 
!     &      + DATE_TIME(8) / 1000.  
!     &      + DATE_TIME(6) * 60.  
!     &      + DATE_TIME(5) * 3600.
!      DELTA_TIME = TIME1 - TIME0
!      WRITE(200,'(1X,"RUN ",I3,3X,F10.3)') RUN, DELTA_TIME
!      TIME0 = TIME1

      IF (CONTROL % ERRCODE > 0) THEN
        WRITE(MSG(1),'(A,I8)') "End of run ", CONTROL % RUN
        WRITE(MSG(2),'("Simulation ended with error code ",I3)') 
     &      CONTROL % ERRCODE
        CALL WARNING(2,'ENDRUN',MSG)
        CALL INFO(2,'ENDRUN',MSG)
      ELSE
        WRITE(MSG(1),'(A,I8)') "Normal end of run ", CONTROL % RUN
        CALL WARNING(0,'ENDRUN',MSG)
        CALL INFO(1,'ENDRUN',MSG)
      ENDIF
      
!     VSH
      if (SOILPROP % NLAYR > maxnlayers ) then
         maxnlayers = SOILPROP % NLAYR
      end if 
C*********************************************************************** 
C***********************************************************************
C     End of Run
C*********************************************************************** 
      ELSE IF (DYNAMIC .EQ. ENDRUN) THEN
        CALL SOIL(CONTROL, ISWITCH, 
     &    ES, FERTDATA, FracRts, HARVRES, IRRAMT,         !Input
     &    KTRANS, KUptake, OMAData, PUptake, RLV,         !Input
     &    SENESCE, ST, SWDELTX,TILLVALS, UNH4, UNO3,      !Input
     &    WEATHER, XHLAI,                                 !Input
     &    FLOODN, FLOODWAT, MULCH, UPFLOW,                !I/O
     &    NH4_plant, NO3_plant, SKi_AVAIL, SNOW,          !Output
     &    SPi_AVAIL, SOILPROP, SomLitC, SomLitE,          !Output
     &    SW, SWDELTS, SWDELTU, UPPM, WINF, YREND)        !Output

!!     Temporary timer function
!      CALL DATE_AND_TIME (VALUES=DATE_TIME)
!      
!!     Convert time to seconds
!      TIME1 = DATE_TIME(7) 
!     &      + DATE_TIME(8) / 1000.  
!     &      + DATE_TIME(6) * 60.  
!     &      + DATE_TIME(5) * 3600.
!      DELTA_TIME = TIME1 - TIME_START
!      WRITE(200,'(/," Total Time",F10.3)') RUN, DELTA_TIME

!      VSH CSV outputs
       IF (ISWITCH % FMOPT == 'C') THEN
          CALL CsvOutputs(CONTROL % MODEL(1:5), CONTROL % N_ELEMS,
     & maxnlayers)
        END IF 

!***********************************************************************
!***********************************************************************
!     END OF DYNAMIC IF CONSTRUCT
!***********************************************************************
      ENDIF
      RETURN
      END SUBROUTINE LAND 

C=======================================================================
      SUBROUTINE TDINT_BOOTSTRAP(TDINT_INIT, TDINT_ON, TDINT_HELPER)
      IMPLICIT NONE

      LOGICAL TDINT_INIT, TDINT_ON
      INTEGER ILEN, ISTAT
      CHARACTER*(*) TDINT_HELPER
      CHARACTER*240 ENVBUF

      IF (TDINT_INIT) RETURN

      TDINT_INIT = .TRUE.
      TDINT_ON = .FALSE.
      TDINT_HELPER = ' '

      ENVBUF = ' '
      CALL GET_ENVIRONMENT_VARIABLE('DSSAT_INTERACTIVE_MODE', ENVBUF,
     &  LENGTH=ILEN, STATUS=ISTAT)
      IF (ISTAT .NE. 0 .OR. ILEN .LE. 0) RETURN
      IF (ENVBUF(1:1) .NE. '1') RETURN

      ENVBUF = ' '
      CALL GET_ENVIRONMENT_VARIABLE('DSSAT_INTERACTIVE_HELPER_COMMAND',
     &  ENVBUF, LENGTH=ILEN, STATUS=ISTAT)
      IF (ISTAT .NE. 0 .OR. ILEN .LE. 0) RETURN
      TDINT_HELPER(1:MIN(LEN(TDINT_HELPER), ILEN)) =
     &  ENVBUF(1:MIN(LEN(TDINT_HELPER), ILEN))
      TDINT_ON = .TRUE.

      RETURN
      END SUBROUTINE TDINT_BOOTSTRAP

C=======================================================================
      SUBROUTINE TDINT_WRITE_READY(TDINT_HELPER, DAS, MDATE, SOILPROP,
     &  SW, NH4_PLANT, NO3_PLANT, WEATHER, XLAI, PSTRES1, NSTRES, EOP)
      USE ModuleDefs
      IMPLICIT NONE

      INTEGER DAS, MDATE
      INTEGER SYS, SYSTEM
      REAL EOP, NSTRES, PSTRES1, XLAI
      REAL, DIMENSION(NL) :: NH4_PLANT, NO3_PLANT, SW
      TYPE (SoilType) SOILPROP
      TYPE (WeatherType) WEATHER
      CHARACTER*(*) TDINT_HELPER
      CHARACTER*512 COMMAND

      CALL TDINT_WRITE_STATE_PAYLOAD(DAS, MDATE, SOILPROP, SW,
     &  NH4_PLANT, NO3_PLANT, WEATHER, XLAI, PSTRES1, NSTRES, EOP)
      COMMAND = TRIM(TDINT_HELPER) //
     &  ' write-ready --state-file transdssat_interactive_state.kv' //
     &  ' --info-tag bridge_stage=reset'
      SYS = SYSTEM(COMMAND)

      RETURN
      END SUBROUTINE TDINT_WRITE_READY

C=======================================================================
      SUBROUTINE TDINT_WRITE_STEP_RESPONSE(TDINT_HELPER, DAS, MDATE,
     &  SOILPROP, SW, NH4_PLANT, NO3_PLANT, WEATHER, XLAI, PSTRES1,
     &  NSTRES, EOP, STEP_INDEX, DAYS_EXECUTED, DONE_FLAG)
      USE ModuleDefs
      IMPLICIT NONE

      LOGICAL DONE_FLAG
      INTEGER DAS, DAYS_EXECUTED, MDATE, STEP_INDEX
      INTEGER SYS, SYSTEM
      REAL EOP, NSTRES, PSTRES1, XLAI
      REAL, DIMENSION(NL) :: NH4_PLANT, NO3_PLANT, SW
      TYPE (SoilType) SOILPROP
      TYPE (WeatherType) WEATHER
      CHARACTER*(*) TDINT_HELPER
      CHARACTER*32 DAYBUF, STEPBUF
      CHARACTER*512 COMMAND

      CALL TDINT_WRITE_STATE_PAYLOAD(DAS, MDATE, SOILPROP, SW,
     &  NH4_PLANT, NO3_PLANT, WEATHER, XLAI, PSTRES1, NSTRES, EOP)

      WRITE(STEPBUF,'(I0)') STEP_INDEX
      WRITE(DAYBUF,'(I0)') DAYS_EXECUTED
      COMMAND = TRIM(TDINT_HELPER) //
     &  ' write-step-response --step-index ' // TRIM(STEPBUF) //
     &  ' --state-file transdssat_interactive_state.kv' //
     &  ' --reward 0.0 --days-executed ' // TRIM(DAYBUF) //
     &  ' --info-tag bridge_stage=step_response'
      IF (DONE_FLAG) THEN
        COMMAND = TRIM(COMMAND) // ' --done'
      ENDIF
      SYS = SYSTEM(COMMAND)

      RETURN
      END SUBROUTINE TDINT_WRITE_STEP_RESPONSE

C=======================================================================
      SUBROUTINE TDINT_WAIT_ACTION(TDINT_HELPER, DAS, MDATE, SOILPROP,
     &  SW, NH4_PLANT, NO3_PLANT, WEATHER, XLAI, PSTRES1, NSTRES,
     &  EOP, STEP_INDEX, DECISION_DAYS, IRRIGATION_MM,
     &  NITROGEN_KG_HA, CLOSE_REQUESTED)
      USE ModuleDefs
      IMPLICIT NONE

      LOGICAL CLOSE_REQUESTED
      INTEGER DAS, MDATE, STEP_INDEX, DECISION_DAYS
      INTEGER SYS, SYSTEM
      REAL EOP, IRRIGATION_MM, NITROGEN_KG_HA, NSTRES, PSTRES1, XLAI
      REAL, DIMENSION(NL) :: NH4_PLANT, NO3_PLANT, SW
      TYPE (SoilType) SOILPROP
      TYPE (WeatherType) WEATHER
      CHARACTER*(*) TDINT_HELPER
      CHARACTER*32 STEPBUF
      CHARACTER*512 COMMAND

      CALL TDINT_WRITE_STATE_PAYLOAD(DAS, MDATE, SOILPROP, SW,
     &  NH4_PLANT, NO3_PLANT, WEATHER, XLAI, PSTRES1, NSTRES, EOP)

      WRITE(STEPBUF,'(I0)') STEP_INDEX
      COMMAND = TRIM(TDINT_HELPER) //
     &  ' await-action --step-index ' // TRIM(STEPBUF) //
     &  ' --output-action-file transdssat_interactive_action.kv'
      SYS = SYSTEM(COMMAND)

      CALL TDINT_READ_ACTION_FILE('transdssat_interactive_action.kv',
     &  DECISION_DAYS, IRRIGATION_MM, NITROGEN_KG_HA,
     &  CLOSE_REQUESTED)

      RETURN
      END SUBROUTINE TDINT_WAIT_ACTION

C=======================================================================
      SUBROUTINE TDINT_WRITE_CLOSE_OUTCOME(TDINT_HELPER)
      IMPLICIT NONE

      INTEGER LUN, SYS, SYSTEM
      CHARACTER*(*) TDINT_HELPER
      CHARACTER*512 COMMAND

      OPEN(NEWUNIT=LUN, FILE='transdssat_interactive_outcome.kv',
     &  STATUS='REPLACE')
      WRITE(LUN,'(A)') 'yield_kg_ha=0.0'
      WRITE(LUN,'(A)') 'biomass_kg_ha=0.0'
      WRITE(LUN,'(A)') 'total_irrigation_mm=0.0'
      WRITE(LUN,'(A)') 'total_nitrogen_kg_ha=0.0'
      WRITE(LUN,'(A)') 'water_use_efficiency=0.0'
      WRITE(LUN,'(A)') 'nitrogen_use_efficiency=0.0'
      WRITE(LUN,'(A)') 'cumulative_reward=0.0'
      CLOSE(LUN)

      COMMAND = TRIM(TDINT_HELPER) //
     &  ' write-final-outcome --outcome-file ' //
     &  'transdssat_interactive_outcome.kv'
      SYS = SYSTEM(COMMAND)

      RETURN
      END SUBROUTINE TDINT_WRITE_CLOSE_OUTCOME

C=======================================================================
      SUBROUTINE TDINT_WRITE_STATE_PAYLOAD(DAS, MDATE, SOILPROP, SW,
     &  NH4_PLANT, NO3_PLANT, WEATHER, XLAI, PSTRES1, NSTRES, EOP)
      USE ModuleDefs
      IMPLICIT NONE

      INTEGER DAS, I, LUN, MDATE, NLAYR, STAGE_INDEX
      REAL CANOPY, EOP, NITROGEN_STRESS, NSTRES, PSTRES1, ROOTWAT
      REAL SOIL_MOISTURE, SOILN, WATER_STRESS, XLAI
      REAL, DIMENSION(NL) :: NH4_PLANT, NO3_PLANT, SW
      TYPE (SoilType) SOILPROP
      TYPE (WeatherType) WEATHER
      CHARACTER*16 STAGE_NAME

      NLAYR = SOILPROP % NLAYR
      ROOTWAT = 0.0
      SOILN = 0.0
      DO I = 1, NLAYR
        ROOTWAT = ROOTWAT + SW(I) * SOILPROP % DLAYR(I)
        SOILN = SOILN + NH4_PLANT(I) + NO3_PLANT(I)
      ENDDO

      IF (SOILPROP % DUL(1) .GT. SOILPROP % LL(1)) THEN
        SOIL_MOISTURE = (SW(1) - SOILPROP % LL(1)) /
     &    (SOILPROP % DUL(1) - SOILPROP % LL(1))
      ELSE
        SOIL_MOISTURE = SW(1)
      ENDIF
      SOIL_MOISTURE = MAX(0.0, MIN(1.0, SOIL_MOISTURE))

      CANOPY = MAX(0.0, MIN(1.0, XLAI / 6.0))
      WATER_STRESS = MAX(0.0, MIN(1.0, PSTRES1))
      NITROGEN_STRESS = MAX(0.0, MIN(1.0, NSTRES))

      STAGE_NAME = 'preplant'
      STAGE_INDEX = 0
      IF (MDATE .GT. 0 .OR. DAS .GT. 0) THEN
        STAGE_NAME = 'in_season'
        STAGE_INDEX = 1
      ENDIF

      OPEN(NEWUNIT=LUN, FILE='transdssat_interactive_state.kv',
     &  STATUS='REPLACE')
      WRITE(LUN,'(A,I0)') 'day_index=', MAX(0, DAS)
      WRITE(LUN,'(A,A)') 'stage=', TRIM(STAGE_NAME)
      WRITE(LUN,'(A,I0)') 'stage_index=', STAGE_INDEX
      WRITE(LUN,'(A,F12.4)') 'soil_moisture=', SOIL_MOISTURE
      WRITE(LUN,'(A,F12.4)') 'root_zone_water_mm=', ROOTWAT
      WRITE(LUN,'(A,F12.4)') 'soil_nitrogen_kg_ha=', SOILN
      WRITE(LUN,'(A,F12.4)') 'canopy_cover=', CANOPY
      WRITE(LUN,'(A,F12.4)') 'biomass_kg_ha=', 0.0
      WRITE(LUN,'(A,F12.4)') 'water_stress=', WATER_STRESS
      WRITE(LUN,'(A,F12.4)') 'nitrogen_stress=', NITROGEN_STRESS
      WRITE(LUN,'(A,F12.4)') 'tmean_c=', WEATHER % TAVG
      WRITE(LUN,'(A,F12.4)') 'precipitation_mm=', WEATHER % RAIN
      WRITE(LUN,'(A,F12.4)') 'et0_mm=', MAX(0.0, EOP)
      WRITE(LUN,'(A,F12.4)') 'radiation_mj_m2=', WEATHER % SRAD
      CLOSE(LUN)

      RETURN
      END SUBROUTINE TDINT_WRITE_STATE_PAYLOAD

C=======================================================================
      SUBROUTINE TDINT_READ_ACTION_FILE(FILENAME, DECISION_DAYS,
     &  IRRIGATION_MM, NITROGEN_KG_HA, CLOSE_REQUESTED)
      IMPLICIT NONE

      LOGICAL CLOSE_REQUESTED, EXISTS
      INTEGER CLOSE_FLAG, DECISION_DAYS, IOS, LUN
      REAL IRRIGATION_MM, NITROGEN_KG_HA
      CHARACTER*(*) FILENAME
      CHARACTER*256 LINE

      DECISION_DAYS = 0
      CLOSE_FLAG = 0
      IRRIGATION_MM = 0.0
      NITROGEN_KG_HA = 0.0
      CLOSE_REQUESTED = .FALSE.

      INQUIRE(FILE=FILENAME, EXIST=EXISTS)
      IF (.NOT. EXISTS) RETURN

      OPEN(NEWUNIT=LUN, FILE=FILENAME, STATUS='OLD', IOSTAT=IOS)
      IF (IOS .NE. 0) RETURN

   10 READ(LUN,'(A)',IOSTAT=IOS) LINE
      IF (IOS .NE. 0) GOTO 20
      IF (INDEX(LINE,'decision_interval_days=') .EQ. 1) THEN
        READ(LINE(24:),*,IOSTAT=IOS) DECISION_DAYS
      ELSEIF (INDEX(LINE,'irrigation_mm=') .EQ. 1) THEN
        READ(LINE(15:),*,IOSTAT=IOS) IRRIGATION_MM
      ELSEIF (INDEX(LINE,'nitrogen_kg_ha=') .EQ. 1) THEN
        READ(LINE(16:),*,IOSTAT=IOS) NITROGEN_KG_HA
      ELSEIF (INDEX(LINE,'close_requested=') .EQ. 1) THEN
        READ(LINE(17:),*,IOSTAT=IOS) CLOSE_FLAG
        CLOSE_REQUESTED = CLOSE_FLAG .NE. 0
      ENDIF
      GOTO 10

   20 CONTINUE
      CLOSE(LUN)

      RETURN
      END SUBROUTINE TDINT_READ_ACTION_FILE
