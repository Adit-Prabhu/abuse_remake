/* Differential-test harness for boundary "inside" flags.
   The two function bodies below are copied verbatim from
   historicalsource/abuse@01cce80 abuse/src/items.c (public domain):
   inside_forward = boundary::boundary(bFILE*) lines 23-97 (the file read and
   endpoint check at lines 9-21 stay in the caller),
   inside_flipped = boundary::boundary(boundary*) lines 103 and 108-182
   (the allocation at lines 104-107 is replaced by the caller's buffer).
   Only the function signatures and this main() are new. */
#include <stdio.h>
#define max(a,b) ((a)>(b)?(a):(b))
#define min(a,b) ((a)<(b)?(a):(b))
static void inside_forward(unsigned char tot, unsigned char *data, unsigned char *inside)
{
  int x1,y1,x2,y2,checkx,checky,i;
  unsigned char *point_on;
  
  for (i=0,point_on=data;i<tot-1;i++)
  {
    x1=*(point_on++);
    y1=*(point_on++);
    x2=point_on[0];    
    y2=point_on[1];
    
    checkx=(x1+x2)/2;
    checky=(y1+y2)/2;

    int j,xp1,yp1,xp2,yp2,maxx,maxy,minx,miny;    
    unsigned char *point2,segs_left=0,segs_right=0,segs_down=0;    
    int skip_next=0;    
    int check_left=0,check_right=0,check_down=0;


    if (y1==y2) check_down=1;
    else if (x1==x2) check_left=1;
    else 
    {
      check_down=1;      
      if (x1<x2) 
        if (y1<y2) check_left=1;
        else check_right=1;
      else if (y1<y2) check_right=1;
      else check_left=1;
    }
    
    maxx=max(x1,x2);
    maxy=max(y1,y2);
    minx=min(x1,x2);
    miny=min(y1,y2);
    
    if (skip_next)
      skip_next=0;
    else
    {            
      for (j=0,point2=data;j<tot-1;j++,point2+=2)
      {	
	if (skip_next)
	  skip_next=0;
	else
	{	  
	  if (j!=i)           // make sure we are not looking at ourself
	  {
	    xp1=point2[0];
	    yp1=point2[1];
	    xp2=point2[2];    
	    yp2=point2[3];      	  	    

	    if ((checkx>=xp1 && checkx<=xp2) || (checkx>=xp2 &&  checkx<=xp1))
            {	      
  	      if (check_down && (yp1>miny && yp2>miny))	      	
		segs_down++;
	      if (checkx==xp2) skip_next=1;	      	      
	    } else if ((checky>=yp1 && checky<=yp2) || (checky>=yp2 &&  checky<=yp1))
	    {
	      if (check_left && xp1<maxx && xp2<maxx)	     
		segs_left++;
	      if (check_right && xp1>minx && xp2>minx)	     
	        segs_right++;
	      if (checky==yp2) skip_next=1;	      
	    }
	  }
	}      
      }      
    }    
    if (!check_down) segs_down=1;
    if (!check_right) segs_right=1;
    if (!check_left) segs_left=1;
       
    inside[i]=!(((segs_left&1)&&(segs_right&1)&&(segs_down&1)));
  }       
}
static void inside_flipped(unsigned char tot, unsigned char *data, unsigned char *inside)
{
  int x1,y1,x2,y2,checkx,checky,i;
  unsigned char *point_on;  
  /* (allocation of inside[] removed: the caller passes the buffer) */
  for (i=0,point_on=data;i<tot-1;i++)
  {
    x1=*(point_on++);
    y1=*(point_on++);
    x2=point_on[0];    
    y2=point_on[1];
    
    checkx=(x1+x2)/2;
    checky=(y1+y2)/2;

    int j,xp1,yp1,xp2,yp2,maxx,maxy,minx,miny;    
    unsigned char *point2,segs_left=0,segs_right=0,segs_down=0;    
    int skip_next=0;    
    int check_left=0,check_right=0,check_down=0;


    if (y1==y2) check_down=1;
    else if (x1==x2) check_right=1;
    else 
    {
      check_down=1;      
      if (x1<x2) 
        if (y1<y2) check_left=1;
        else check_right=1;
      else if (y1<y2) check_right=1;
      else check_left=1;
    }



    maxx=max(x1,x2);
    maxy=max(y1,y2);
    minx=min(x1,x2);
    miny=min(y1,y2);
    
    if (skip_next)
      skip_next=0;
    else
    {            
      for (j=0,point2=data;j<tot-1;j++,point2+=2)
      {	
	if (skip_next)
	  skip_next=0;
	else
	{	  
	  if (j!=i)           // make sure we are not looking at ourself
	  {
	    xp1=point2[0];
	    yp1=point2[1];
	    xp2=point2[2];    
	    yp2=point2[3];      	  	    

	    if ((checkx>=xp1 && checkx<=xp2) || (checkx>=xp2 &&  checkx<=xp1))
            {	      
  	      if (check_down && (yp1>miny && yp2>miny))	      	
		segs_down++;
	      if (checkx==xp2) skip_next=1;	      	      
	    } else if ((checky>=yp1 && checky<=yp2) || (checky>=yp2 &&  checky<=yp1))
	    {
	      if (check_left && xp1<maxx && xp2<maxx)	     
		segs_left++;
	      if (check_right && xp1>minx && xp2>minx)	     
	        segs_right++;
	      if (checky==yp2) skip_next=1;	      
	    }
	  }
	}      
      }      
    }    
    if (!check_down) segs_down=1;
    if (!check_right) segs_right=1;
    if (!check_left) segs_left=1;
       
    inside[i]=!(((segs_left&1)&&(segs_right&1)&&(segs_down&1)));
  }       
}

/* stdin: lines of "tot x0 y0 x1 y1 ..."; stdout: forward flags, then flipped flags */
int main(void)
{
  int tot;
  while (scanf("%d", &tot) == 1)
  {
    unsigned char data[512], fwd[256], flp[256];
    int i, v;
    for (i = 0; i < tot * 2; i++) { scanf("%d", &v); data[i] = (unsigned char)v; }
    inside_forward((unsigned char)tot, data, fwd);
    inside_flipped((unsigned char)tot, data, flp);
    for (i = 0; i < tot - 1; i++) printf("%d ", fwd[i]);
    printf("|");
    for (i = 0; i < tot - 1; i++) printf(" %d", flp[i]);
    printf("\n");
  }
  return 0;
}
