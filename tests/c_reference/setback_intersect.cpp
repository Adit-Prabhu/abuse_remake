/* Differential-test harness for setback_intersect.
   The function below is copied verbatim from historicalsource/abuse@01cce80
   abuse/src/intsect.c lines 139-233 (public domain). It takes C++ references,
   so this file is compiled as C++. Only main() is new.
   stdin: "x1 y1 x2 y2 xp1 yp1 xp2 yp2 inside" per line; stdout: "ret x2 y2". */
#include <stdio.h>
#include <stdlib.h>
int setback_intersect(long x1,long y1,long &x2,long &y2,
		      long xp1, long yp1, long xp2, long yp2, 
                     long inside)  // which side is inside the polygon? (0 always setback)
{
  // the line equations will be put in the form
  // x(y2-y1)+y(x1-x2)-x1*y2+x2*y1=0
  //     A        B        C  

  long a1,b1,c1,a2,b2,c2,r1,r2;              

  a1=y2-y1;        
  b1=x1-x2;        
  c1=-x1*y2+x2*y1; 

  if (yp1<yp2 || (yp1==yp2 && xp1>xp2))    // use only increasing functions
  {    
    r1=yp1; yp1=yp2; yp2=r1;        // swap endpoints if wrong order
    r1=xp1; xp1=xp2; xp2=r1;
  } 

  long xdiff,ydiff;
/*  long xdiff=abs(xp1-xp2),ydiff=yp1-yp2;  
  if (xdiff>=ydiff)                              // increment the endpoints 
    if (xp2<xp1) { xp2--; xp1++; }  				 
    else { xp2++; xp1--; } 
  
  if (xdiff<=ydiff)
  {
    yp1++;    
    yp2--;
  } */
  

  r1=xp1*a1+yp1*b1+c1;
  r2=xp2*a1+yp2*b1+c1;

  if ((r1^r2)<=0 || r1==0 || r2==0)           // signs must be different to intersect
  {
    a2=yp2-yp1;  
    b2=xp1-xp2;  
    c2=-xp1*yp2+xp2*yp1;        
    r1=x1*a2+y1*b2+c2;
    r2=x2*a2+y2*b2+c2;

    if ((r1^r2)<=0 || r1==0 || r2==0)
    {
      if ( ((xp1<xp2) && ((r2^inside)>0)) || 
           (xp1>=xp2 && ((r2^inside)<0)) ||
	   inside==0 || r2==0) 
      { 
	long ae=a1*b2,bd=b1*a2;	
	if (ae!=bd)         // co-linear returns 0
	{
	  x2=(b1*c2-b2*c1)/(ae-bd);
	  y2=(a1*c2-a2*c1)/(bd-ae);	  
	  xdiff=abs(x2-x1);
	  ydiff=abs(y2-y1);	  
//	  if (xdiff<=ydiff)            // push the intersection back one pixel
//	  {
	    if (y2!=y1)
	    {	      
  	      if (y2>y1)
	        y2--;
	      else y2++;
	    }
//	  } 
//	  if (xdiff>=ydiff)
//	  {
	    if (x2!=x1)
	    {
	      if (x2>x1)
	        x2--;
	      else x2++;
	    }
//	  }

	  if (inside)        // check to make sure end point is on the 
	  {                  // right side
	    r1=x1*a2+y1*b2+c2;	    
	    r2=x2*a2+y2*b2+c2;	    
	    if ((r2!=0 && ((r1^r2)<0)))
	    {	      
	      x2=x1;
	      y2=y1;
	    }	  
	  }		
	  return 1;	  
	}
      }
    }    
  } 
  return 0;
    
}


int main(void)
{
  long x1,y1,x2,y2,xp1,yp1,xp2,yp2,inside;
  while (scanf("%ld %ld %ld %ld %ld %ld %ld %ld %ld",&x1,&y1,&x2,&y2,&xp1,&yp1,&xp2,&yp2,&inside)==9)
  {
    int r=setback_intersect(x1,y1,x2,y2,xp1,yp1,xp2,yp2,inside);
    printf("%d %ld %ld\n",r,x2,y2);
  }
  return 0;
}
